from api._vercel_common import JsonHandler, proxy


class handler(JsonHandler):
    def do_GET(self):
        self.send_json(200, {
            "ok": True,
            "rapidapi_key_configured": bool(proxy.RAPIDAPI_KEY),
            "provider_host": proxy.RAPIDAPI_HOST,
        })
