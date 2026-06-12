import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path("d:/Works/GenericAgent/DesktopAgenticSystem").resolve()
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "apps" / "api_gateway"))
sys.path.insert(0, str(root_dir / "apps" / "das_core"))

from core.common_data_area import CommonDataArea
from settings.config_loader import load_settings_into_cda
from whatsapp_gateways.whatsapp_service import WhatsAppFolderService
from whatsapp_gateways.whatsapp_controller import WhatsAppController

cda = CommonDataArea()
load_settings_into_cda(cda)

controller = WhatsAppController(cda, None)
svc = WhatsAppFolderService(cda, controller)

print("Root dir:", svc._root_dir())
print("Paths received:", svc._paths()["received"])
