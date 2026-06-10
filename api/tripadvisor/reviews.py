from api._vercel_common import JsonHandler, first_param, int_param, proxy


class handler(JsonHandler):
    def do_GET(self):
        params = self.query_params()
        city = first_param(params, "city")
        name = first_param(params, "name")
        category = first_param(params, "category", default="attractions")
        content_id = first_param(params, "contentId", "content_id")
        limit = int_param(params, "limit", 8, 1, 20)
        if not city and not content_id:
            self.send_json(400, {"ok": False, "error": "city or contentId is required"})
            return
        try:
            self.send_json(200, proxy.tripadvisor_reviews(city, name, category, content_id, limit))
        except Exception as exc:
            self.send_exception(exc)
