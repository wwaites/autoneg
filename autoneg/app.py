__all__ = ['AutoNeg']

from pprint import pformat
from traceback import format_exc
from optparse import OptionParser
from ConfigParser import ConfigParser
import os, time

from autoneg.accept import negotiate

BUFSIZ = 4096

class AutoNeg(object):
    opt_parser = OptionParser(usage="%prog options")
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
