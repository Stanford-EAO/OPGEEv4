from ..log import getLogger
from ..process import Process
from ..stream import PHASE_LIQUID

_logger = getLogger(__name__)


# A temporary "end process" for testing. Used in opgee.xml.
class GasReinjectionWell(Process):
    def run(self, analysis):
        self.print_running_msg()