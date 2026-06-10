from api._vercel_common import JsonHandler, first_param, int_param, proxy


class handler(JsonHandler):
    def do_GET(self):
        params = self.query_params()
        city = first_param(params, "city")
        limit = int_param(params, "limit", 3, 1, 10)
        if not city:
            self.send_json(400, {"ok": False, "error": "city is required"})
            return
        try:
            self.send_json(200, proxy.tripadvisor_hotels(city, limit))
        except Exception as exc:
            self.send_exception(exc)
