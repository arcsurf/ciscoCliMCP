import os
import sys
import logging

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools_show import register_show_tools
from tools_config import register_config_tools
from tools_diag import register_diag_tools
from resources import register_resources
from prompts import register_prompts

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(message)s"
)

mcp = FastMCP("Cisco Router MCP")

DEFAULTS = {
    "device_type": os.getenv("CISCO_DEFAULT_DEVICE_TYPE", "cisco_ios"),
    "username": os.getenv("CISCO_USERNAME"),
    "password": os.getenv("CISCO_PASSWORD"),
    "secret": os.getenv("CISCO_ENABLE_SECRET"),
    "inventory_csv": os.getenv("CISCO_INVENTORY_CSV", "inventory.csv"),
    "lab_mode": os.getenv("CISCO_LAB_MODE", "false").lower() == "true",
    "read_timeout": int(os.getenv("CISCO_READ_TIMEOUT", "120")),
}

register_show_tools(mcp, DEFAULTS)
register_config_tools(mcp, DEFAULTS)
register_diag_tools(mcp, DEFAULTS)
register_resources(mcp)
register_prompts(mcp)

if __name__ == "__main__":
    mcp.run()