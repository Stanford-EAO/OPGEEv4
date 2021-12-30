"""
.. OPGEE "run" sub-command

.. Copyright (c) 2021 Richard Plevin and Stanford University
   See the https://opensource.org/licenses/MIT for license details.
"""
from ..subcommand import SubcommandABC, clean_help
from ..log import getLogger

_logger = getLogger(__name__)

class RunCommand(SubcommandABC):
    def __init__(self, subparsers, name='run', help='Run the specified portion of an OPGEE LCA model'):
        kwargs = {'help' : help}
        super(RunCommand, self).__init__(name, subparsers, kwargs)

    def addArgs(self, parser):
        from ..utils import ParseCommaList

        parser.add_argument('-a', '--analyses', action=ParseCommaList,
                            help=clean_help('''Run only the specified analysis or analyses. Argument may be a 
                            comma-delimited list of Analysis names.'''))

        parser.add_argument('-f', '--fields', action=ParseCommaList,
                            help=clean_help('''Run only the specified field or fields. Argument may be a 
                            comma-delimited list of Field names. To specify a field within a specific Analysis,
                            use the syntax "analysis_name.field_name". Otherwise the field will be run for each
                            Analysis the field name occurs within (respecting the --analyses flag).'''))

        parser.add_argument('-m', '--model-file',
                            help=clean_help('''An XML model definition file to load. If --no_default_model is *not* specified,
                            (i.e., the default model is loaded), the XML file specified here will be merged with the default
                            model.'''))

        parser.add_argument('-n', '--no-default-model', action='store_true',
                            help=clean_help('''Don't load the built-in opgee.xml model definition.'''))

        return parser

    def run(self, args, tool):
        from ..error import CommandlineError
        from ..model import ModelFile
        from ..pkg_utils import resourceStream

        use_default_model = not args.no_default_model
        model_file = args.model_file
        field_names = args.fields
        analysis_names = args.analyses

        if not (field_names or analysis_names):
            raise CommandlineError("Must indicate one or more fields or analyses to run")

        if not (use_default_model or model_file):
            raise CommandlineError("No model to run: the --model_file option was not used and --no_default_model was specified.")

        builtin_model = user_model = None

        if use_default_model:
            s = resourceStream('etc/opgee.xml', stream_type='bytes', decode=None)
            mf = ModelFile('[opgee]/etc/opgee.xml', stream=s)
            builtin_model = mf.model

        if model_file:
            mf = ModelFile(model_file)
            user_model = mf.model

        # TBD: remove this after writing merge that works at the XML level
        def merge_models(model1, model2):
            # if one or the other is None, return the other
            if not (model1 and model2):
                return model1 or model2 or None

            # TBD: do the actual merge
            return None

        model = merge_models(builtin_model, user_model)
        model.validate()

        all_analyses = model.analyses()
        if analysis_names:
            selected_analyses = [ana for ana in all_analyses if ana.name in analysis_names]
            if not selected_analyses:
                raise CommandlineError(f"Specified analyses {analysis_names} were not found in model")
        else:
            selected_analyses = list(all_analyses)

        if field_names:
            specific_field_tuples = [name.split('.') for name in field_names if '.' in name] # tuples of (analysis, field)
            nonspecific_field_names = [name for name in field_names if '.' not in name]

            selected_fields = []    # list of tuples of (analysis_name, field_name)

            for analysis in selected_analyses:
                found = [(field, analysis) for field in analysis.fields() if field.name in nonspecific_field_names]
                selected_fields.extend(found)

            for analysis_name, field_name in specific_field_tuples:
                analysis = model.get_analysis(analysis_name)
                field = analysis.get_field(field_name)
                if field is None:
                    raise CommandlineError(f"Field '{field_name}' was not found in analysis '{analysis_name}'")

                selected_fields.append((field, analysis))

            if not selected_fields:
                raise CommandlineError("The model contains no fields matching command line arguments.")
        else:
            # run all fields for selected analyses
            selected_fields = [(field, analysis) for analysis in selected_analyses for field in analysis.fields()]

        for field, analysis in selected_fields:
            field.run(analysis)
            field.report(analysis)
