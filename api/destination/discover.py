from datetime import date

from api._vercel_common import JsonHandler, first_param, int_param, proxy


class handler(JsonHandler):
    def do_GET(self):
        params = self.query_params()
        origin = first_param(params, "origin")
        limit = int_param(params, "limit", 6, 1, 8)
        try:
            month = int(first_param(params, "month", default=str(date.today().month)))
        except ValueError:
            month = date.today().month
        try:
            self.send_json(200, proxy.destination_discover(month, origin, limit))
        except Exception as exc:
            self.send_exception(exc)
