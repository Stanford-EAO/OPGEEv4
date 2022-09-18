"""
.. OPGEE "run" sub-command

.. Copyright (c) 2021 Richard Plevin and Stanford University
   See the https://opensource.org/licenses/MIT for license details.
"""
from ..subcommand import SubcommandABC
from ..log import getLogger
from ..error import OpgeeException

_logger = getLogger(__name__)

class RunCommand(SubcommandABC):
    def __init__(self, subparsers, name='run', help='Run the specified portion of an OPGEE LCA model'):
        kwargs = {'help' : help}
        super(RunCommand, self).__init__(name, subparsers, kwargs)

    def addArgs(self, parser):
        from ..utils import ParseCommaList

        parser.add_argument('-a', '--analyses', action=ParseCommaList,
                            help='''Run only the specified analysis or analyses. Argument may be a 
                            comma-delimited list of Analysis names.''')

        parser.add_argument('-c', '--save-comparison',
                            help='''The name of a CSV file to which to save results suitable for 
                                use with the "compare" subcommand.''')

        parser.add_argument('-f', '--fields', action=ParseCommaList,
                            help='''Run only the specified field or fields. Argument may be a 
                            comma-delimited list of Field names. To specify a field within a specific 
                            Analysis, use the syntax "analysis_name.field_name". Otherwise the field 
                            will be run for each Analysis the field name occurs within (respecting the
                            --analyses flag).''')

        parser.add_argument('-i', '--ignore-errors', action='store_true',
                            help='''Keep running even if some fields raise errors when run''')

        parser.add_argument('-m', '--model-file', action='append',
                            help='''XML model definition files to load. If --no_default_model is *not* 
                                specified, the built-in files etc/opgee.xml and etc/attributes.xml are 
                                loaded first, and the XML files specified here will be merged with these.
                                If --no_default_model is specified, only the given files are loaded;
                                they are merged in the order stated.''')

        parser.add_argument('-n', '--no-default-model', action='store_true',
                            help='''Don't load the built-in opgee.xml model definition.''')

        parser.add_argument('-o', '--output',
                            help='''Write CI output to specified CSV file for all top-level processes 
                            and aggregators, for all fields run''')

        parser.add_argument('-p', '--processes',
                            help='''Write CI output to specified CSV file for all processes, for all fields 
                                run, rather than by top-level processes and aggregators (as with --output)''')

        return parser

    def run(self, args, tool):
        from ..error import CommandlineError
        from ..model_file import ModelFile

        use_default_model = not args.no_default_model
        model_files = args.model_file
        field_names = args.fields
        analysis_names = args.analyses

        if not (field_names or analysis_names):
            raise CommandlineError("Must indicate one or more fields or analyses to run")

        if not (use_default_model or model_files):
            raise CommandlineError("No model to run: the --model-file option was not used and --no-default-model was specified.")

        mf = ModelFile(model_files, use_default_model=use_default_model)
        model = mf.model

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

        errors = []  # accumulate these to print again at the end

        for field, analysis in selected_fields:
            try:
                field.run(analysis)
                field.report()
            except OpgeeException as e:
                if args.ignore_errors:
                    _logger.error(f"Error in {field}: {e}")
                    errors.append((field, e))
                else:
                    raise

        if errors:
            print("\nErrors:")

            for field, e in errors:
                print(f"{field}: {e}")

        if args.output:
            model.save_results(selected_fields, args.output)

        if args.processes:
            model.save_results(selected_fields, args.processes, by_process=True)

        if args.save_comparison:
            model.save_for_comparison(selected_fields, args.save_comparison)
