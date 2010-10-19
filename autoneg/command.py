from autoneg.app import AutoNeg

def autoneg_cgi():
    from flup.server.cgi import WSGIServer
    WSGIServer(AutoNeg()).run()

def autoneg_fcgi():
    from flup.server.fcgi import WSGIServer
    WSGIServer(AutoNeg(), multiplexed=False).run()
