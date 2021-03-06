from opgee.config import pathjoin
from opgee.model_file import ModelFile
from opgee.process import Process

class ProcA(Process):
    def run(self, analysis):
        pass

class ProcB(Process):
    def run(self, analysis):
        pass

class Before(Process):
    def run(self, analysis):
        pass

    def impute(self):
        pass

class Output(Process):
    def run(self, analysis):
        pass

def path_to_test_file(filename):
    path = pathjoin(__file__, '..', f'files/{filename}', abspath=True)
    return path

def load_test_model(xml_file, add_stream_components=False, use_class_path=False, use_default_model=False):
    xml_path = path_to_test_file(xml_file)
    mf = ModelFile(xml_path,
                   add_stream_components=add_stream_components,
                   use_class_path=use_class_path,
                   use_default_model=use_default_model)
    return mf.model
