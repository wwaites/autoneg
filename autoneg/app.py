"""
:program:`autoneg_fcgi`

:program:`autoneg_cgi`

The script need to know the following:

  * mime_type -> extension mapping
  * base directory to look for the files in the filesystem
  * name of the script to strip from request URIs

There is a default set of *mime_types* which might be good
for some purposes but it will usually be desirable to put them
in a configuration file.

If you have a file called *conf.py* with::

  { "mime_types" : [ ("text/plain", ["txt"]), ("text/html", ["html"]) ] }

And then run the cgi with::

  % autoneg_cgi -c conf.py

It will look for text files with the extension .txt and html
files with the extension .html.

Autonegotiation is done by first taking into account the client's 
preferences as expressed in the HTTP Accept header and then the
server's preferences as configured.

Parameters such as *base* and *script* may be configured either
in the configuration file or passed on the command line.

Running a fast-cgi service can be done with *spawn-fcgi* which
should be available for most operating systems. A content
negotiation layer over /var/www might be started with

  % spawn-fcgi -P /tmp/test.pid -s /tmp/test.sock -M 0666 \
    -- autoneg_fcgi -c conf.py -b /var/www

And then the web server would be configured to pass requests
which it couldn't handle to this script over the */tmp/test.sock*
socket.
"""



__all__ = ['AutoNeg']

from traceback import format_exc
from pprint import pformat
from optparse import OptionParser
from ConfigParser import ConfigParser
import os, sys, time
import logging
from glob import glob

from autoneg.accept import negotiate

log = logging.getLogger("autoneg")

BUFSIZ = 4096

class AutoNeg(object):
    opt_parser = OptionParser(usage=__doc__)
    opt_parser.add_option("-c", "--config",
                          dest="config",
                          default=None,
                          help="configuration file")
    opt_parser.add_option("-d", "--debug",
                          dest="debug",
                          default=False,
                          action="store_true",
                          help="debug")
    opt_parser.add_option("-b", "--base",
                          dest="base",
                          help="base path")
    opt_parser.add_option("-s", "--script",
                          dest="script",
                          help="script name to strip")
    opt_parser.add_option("-i", "--index",
                          dest="index",
                          help="index file to use (default: index)")
    opt_parser.add_option("-l", "--logfile",
                          dest="logfile", default=None,
                          help="log to file")
    opt_parser.add_option("-v", "--verbosity",
                          dest="verbosity", default="info",
                          help="log verbosity. one of debug, info, warning, error, critical")
    config = { 
        "mime_types" : [
            ("text/plain", ["txt"]),
            ("text/html", ["html"]),
            ],
        "base": "/var/www",
        "script": "",
        "index": "index",
        "loglevel": "info",
        "logformat": "%(asctime)s %(levelname)s  [%(name)s] %(message)s",
        "methods": ('HEAD', 'GET'),
        }
    def __init__(self):
        self.opts, self.args = self.opt_parser.parse_args()
        if self.opts.config:
            fp = open(self.opts.config)
            cfg = eval(fp.read())
            fp.close()
            self.config.update(cfg)
        self.config["mime_types"] = [ct.split("/", 1) + [exts]
                                     for (ct, exts) in self.config["mime_types"]]

        for k,v in self.opts.__dict__.items():
            if v: self.config[k] = v

        ## set up logging
        logcfg = { 
            "format": self.config.get("logformat"),
            }
        if self.config.get("logfile"):
            logcfg["filename"] = self.config.get("logfile")

        levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL
            }
        logcfg["level"] = levels.get(self.config.get("loglevel"), logging.NOTSET)
        logging.basicConfig(**logcfg)

        log.info("%s starting up", self.__class__.__name__)

    def __call__(self, environ, start_response):
        try:
            method = environ.get('REQUEST_METHOD', 'GET')
            if method.upper() not in self.config["methods"]:
                start_response('405 Method Not Allowed')
                return ['405 Method Not Allowed']
            accept = environ.get('HTTP_ACCEPT', '*/*')
            negotiated = negotiate(self.config["mime_types"], accept)
            return self.request(environ, start_response, method, negotiated)
        except:
            log.error("%s %s %s exception:\n%s" % (environ.get("REMOTE_ADDR"), 
                                                   environ.get("REQUEST_METHOD"),
                                                   environ.get("DOCUMENT_URI", "/"),
                                                   format_exc()))
            log.error("%s %s %s environ:\n%s" % (environ.get("REMOTE_ADDR"), 
                                                 environ.get("REQUEST_METHOD"),
                                                 environ.get("DOCUMENT_URI", "/"),
                                                 pformat(environ)))

            start_response('500 Internal Server Error',
                           [('Content-Type', 'text/plain; charset=utf-8')])
            if self.opts.debug:
                return [format_exc()]
            else:
                return ["Oops. The admin should look at the logs"]

    def get_path(self, environ):
        path = environ.get("DOCUMENT_URI", "/")

        script_name = self.config["script"]
        if path.startswith(script_name):
            path = path[len(script_name):]
        if path.startswith("/"):
            path = path[1:]

        path = os.path.join(self.config["base"], path)
        if os.path.isdir(path):
            path = os.path.join(path, self.config["index"])

        return path

    def request(self, environ, start_response, method, negotiated):
        path = self.get_path(environ)
        for content_type, exts in negotiated:
            for ext in exts:
                fname = path + "." + ext
                if os.path.isfile(fname):
                    try:
                        fp = open(fname)
                        st = os.fstat(fp.fileno())
                        headers = [
                            ('Content-Type', content_type),
                            ('Content-Length', "%s" % st.st_size),
                            ('Content-Location', os.path.basename(fname)),
                            ('Last-Modified', time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                                            time.gmtime(st.st_mtime))),
                            ('Vary', 'Accept'),
                            ('ETag', '%s' % st.st_mtime),
                            ]
                        start_response('200 OK', headers)
                        if method == 'GET':
                            while True:
                                data = fp.read(BUFSIZ)
                                if data: yield data
                                else:
                                    fp.close()
                                    return
                        else:
                            yield "\n"
                    except KeyError:
                        continue

        matches = glob(path + ".*")
        if matches:
            log.warn("%s %s %s with %s" % (environ.get("REMOTE_ADDR"),
                                           environ.get("REQUEST_METHOD"),
                                           environ.get("DOCUMENT_URI", "/"),
                                           accept))
            log.debug("%s %s %s environ:\n%s" % (environ.get("REMOTE_ADDR"), 
                                                 environ.get("REQUEST_METHOD"),
                                                 environ.get("DOCUMENT_URI", "/"),
                                                 pformat(environ)))
            start_response('406 Not Acceptable',
                           [('Content-type', 'text/html')])
            yield """\
<html>
  <head><title>406 Not Acceptable</title></title>
  <body>
    <h1>406 Not Acceptable</h1>
    <p>The requested resource cound not be found in an acceptable form.
       Possible alternatives:</p>
    <ul>
"""
            for m in matches:
                fname = os.path.basename(m)
                yield '      <li><a href="%s">%s</a></li>\n' % (fname, fname)

            yield """\
    </ul>
  </body>
</html>
"""
        else:
            start_response('404 Not Found',
                           [('Content-type', 'text/html')])
            yield """\
<html>
  <head><title>404 Not Found</title></head>
  <body>
    <h1>404 Not Found</h1>
    <p>Sorry, couldn't find what you were looking for</p>
  </body>
</html>
"""


class RdfAutoNeg(AutoNeg):
    opt_parser = OptionParser(usage=__doc__)
    opt_parser.add_option("-c", "--config",
                          dest="config",
                          default=None,
                          help="configuration file")
    opt_parser.add_option("-d", "--debug",
                          dest="debug",
                          default=False,
                          action="store_true",
                          help="debug")
    opt_parser.add_option("-a", "--aliases",
                          dest="aliases",
                          action="append",
                          help="aliases for this host")
    opt_parser.add_option("-n", "--name",
                          dest="hostname",
                          help="canonical hostname for this site")
    opt_parser.add_option("-s", "--script",
                          dest="script",
                          help="script name to strip")
    opt_parser.add_option("-l", "--logfile",
                          dest="logfile", default=None,
                          help="log to file")
    opt_parser.add_option("-v", "--verbosity",
                          dest="verbosity", default="info",
                          help="log verbosity. one of debug, info, warning, error, critical")
    config = { 
        "mime_types" : [
            ("application/rdf+xml", ["rdf", "owl"]),
            ("application/x-ntriples", ["nt"]),
            ("text/n3", ["n3"]),
            ("text/rdf+n3", ["n3"]),
            ],
        "script": "",
        "loglevel": "info",
        "logformat": "%(asctime)s %(levelname)s  [%(name)s] %(message)s",
        "methods": ('HEAD', 'GET'),
        }

    # dictionary of content-types to rdflib serialisations
    serialisations = {
        "application/rdf+xml" : "pretty-xml",
        "application/x-ntriples": "nt",
        "text/n3": "n3",
        "text/rdf+n3": "n3",
        }
    def __init__(self, *av, **kw):
        super(RdfAutoNeg, self).__init__(*av, **kw)
        try:
            from rdflib.graph import Graph
            from rdflib.store import Store
            from rdflib.plugin import get as get_plugin
        except ImportError:
            log.error("You must install rdflib 3.0 or greater to use these facilities")
            sys.exit(1)
        cls = get_plugin(self.config["rdflib.store"], Store)
        self.store = cls(self.config["rdflib.args"])

    def get_path(self, environ):
        ## do a little rewriting of the request
        path = environ.get("DOCUMENT_URI", "/")

        ## strip the script name
        script_name = self.config["script"]
        if path.startswith(script_name):
            path = path[len(script_name):]
        if path.startswith("/"):
            path = path[1:]

        ## if aliases are configured, rewrite to canonical hostname
        hostname = environ["HTTP_HOST"]
        if hostname in self.config.get("aliases", []):
            hostname = self.config.get("hostname")
            if hostname is None:
                raise KeyError("must configure hostname to use aliases")

        return "%s://%s/%s" % (environ.get("wsgi.url_scheme", "http"), hostname, path)

    def request(self, environ, start_response, method, negotiated):
        from rdflib.graph import Graph
        from rdflib.term import URIRef

        negotiated = list(negotiated)

        # we have to invert the autoneg dictionary first to check
        # if the request we have ends with one of the file extensions
        # that is was asked for directly
        extmap = {}
        for content_type, extlist in negotiated:
            [extmap.setdefault(ext, content_type) for ext in extlist]

        # get the graph uri that has been requested
        path = self.get_path(environ)

        # if it ends with an extension, use that
        for ext, content_type in extmap.items():
            if path.endswith("." + ext):
                path = path[:-len(ext)-1]
                break
            content_type = None

        # otherwise use the content-negotiation
        if content_type is None:
            content_type = negotiated[0][0]

        # initialise the graph over the store
        g = Graph(self.store, identifier=URIRef(path))

        # send the serialised graph
        start_response('200 OK', [
                ("Content-type", content_type),
                ("Vary", "Accept"),
                ])
        yield g.serialize(format=self.serialisations.get(content_type, "pretty-xml"))
