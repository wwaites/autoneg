"""
:program:`autoneg_fcgi` :program:`autoneg_cgi`
----------------------------------------------
This is a simple (fast) CGI application that performs HTTP
auto-negotiation and serves files staticly.

It needs to know the following:

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

from pprint import pformat
from traceback import format_exc
from optparse import OptionParser
from ConfigParser import ConfigParser
import os, time

from autoneg.accept import negotiate

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
    config = { 
        "mime_types" : [
            ("text/plain", ["txt"]),
            ("text/html", ["html"]),
            ],
        "base": "/var/www",
        "script": "",
        "index": "index",
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

    def __call__(self, environ, start_response):
        try:
            method = environ.get('REQUEST_METHOD', 'GET')
            if method not in ('HEAD', 'GET'):
                start_response('405 Method Not Allowed')
                return ['405 Method Not Allowed']
            return self.get_autonegotiated(environ, start_response, method)
        except:
            if self.opts.debug:
                start_response('500 Internal Server Error',
                               [('Content-Type', 'text/plain; charset=utf-8')])
                return [format_exc()]
            else:
                raise

    def get_autonegotiated(self, environ, start_response, method):
        path = environ.get("PATH_INFO", "/")

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
                            ('Last-Modified', time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                                            time.gmtime(st.st_mtime))),
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

        start_response('406 Not Acceptable',
                       [('Content-type', 'text/plain')])
        yield """\
    406 Not Acceptable

    The requested resource cound not be found in an acceptable form\n\n"""
