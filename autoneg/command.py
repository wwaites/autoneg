from autoneg.app import AutoNeg, RdfAutoNeg

def autoneg_cgi():
    from flup.server.cgi import WSGIServer
    WSGIServer(AutoNeg()).run()

def autoneg_fcgi():
    from flup.server.fcgi import WSGIServer
    WSGIServer(AutoNeg(), multiplexed=False).run()

def rdfan_cgi():
    from flup.server.cgi import WSGIServer
    WSGIServer(RdfAutoNeg()).run()

def rdfan_fcgi():
    from flup.server.fcgi import WSGIServer
    WSGIServer(RdfAutoNeg(), multiplexed=False).run()
