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
import os, time
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
        if self.opts.base:
            self.config["base"] = self.opts.base
        if self.opts.script:
            self.config["script"] = self.opts.script
        if self.opts.index:
            self.config["index"] = self.opts.index
        if self.opts.logfile:
            self.config["logfile"] = self.opts.logfile
        if self.opts.verbosity:
            self.config["loglevel"] = self.opts.verbosity

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

    def __call__(self, environ, start_response):
        try:
            method = environ.get('REQUEST_METHOD', 'GET')
            if method not in ('HEAD', 'GET'):
                start_response('405 Method Not Allowed')
                return ['405 Method Not Allowed']
            return self.get_autonegotiated(environ, start_response, method)
        except:
            log.error("%s %s %s exception:\n%s" % (environ.get("REMOTE_ADDR"), 
                                                   environ.get("REQUEST_METHOD"),
                                                   environ.get("DOCUMENT_URI", "/"),
                                                   format_exc()))
            log.error("%s %s %s environ:\n%s" % (environ.get("REMOTE_ADDR"), 
                                                 environ.get("REQUEST_METHOD"),
                                                 environ.get("DOCUMENT_URI", "/"),
                                                 pformat(environ)))

            if self.opts.debug:
                start_response('500 Internal Server Error',
                               [('Content-Type', 'text/plain; charset=utf-8')])
                return [format_exc()]
            else:
                raise

    def get_autonegotiated(self, environ, start_response, method):
        path = environ.get("DOCUMENT_URI", "/")

        script_name = self.config["script"]
        if path.startswith(script_name):
            path = path[len(script_name):]
        if path.startswith("/"):
            path = path[1:]

        path = os.path.join(self.config["base"], path)
        if os.path.isdir(path):
            path = os.path.join(path, self.config["index"])

        accept = environ.get('HTTP_ACCEPT', '*/*')
        negotiated = negotiate(self.config["mime_types"], accept)

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
