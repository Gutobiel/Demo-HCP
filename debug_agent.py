import os
import django
import traceback

os.environ['DJANGO_SETTINGS_MODULE'] = 'hcpneus_demo.settings'
django.setup()

from atendimento.hc_agent import HCPneusAI
from agno.vectordb.lancedb import LanceDb
import inspect

print("LanceDb source file:", inspect.getfile(LanceDb))
print("LanceDb init signature:", inspect.signature(LanceDb.__init__))

try:
    print("Attempting to build agent...")
    agent = HCPneusAI.build_agent('test_session_debug')
    print("Agent built successfully")
except Exception:
    traceback.print_exc()
