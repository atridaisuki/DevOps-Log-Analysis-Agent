"""Tool registry — single place to get all agent tools."""

from app.tools.check_metrics import check_metrics
from app.tools.list_services import list_services
from app.tools.query_logs_by_time import query_logs_by_time
from app.tools.read_file import read_file
from app.tools.save_report import save_report
from app.tools.search_logs import search_logs

ALL_TOOLS = [search_logs, query_logs_by_time, read_file, list_services, check_metrics, save_report]
