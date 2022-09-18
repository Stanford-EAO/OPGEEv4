#
# Generate and compare CSV files of process-level results for a set of fields.
# Usually used to compare with similar output from Excel (OPGEEv3) and here (OPGEEv4).
#
from enum import Enum
from opgee.subcommand import SubcommandABC

# Convert OPGEEv3 (Excel) process names to OPGEEv4 names
process_translator = {
    'Acid gas removal' : 'AcidGasRemoval',
    'CO2 gas reinjection compressor' : 'GasReinjectionCompressor',
    'CO2 membrane' : 'CO2Membrane',
    #'Chiller' : '',
    'Crude oil dewatering' : 'CrudeOilDewatering',
    'Crude oil stabilization' : 'CrudeOilStabilization',
    'Crude oil storage' : 'CrudeOilStorage',
    'Crude oil transport' : 'CrudeOilTransport',
    # 'Demethanizer' : 'Demethanizer',
    # 'Diluent transport' : '',
    'Downhole pump (Lifting)' : 'DownholePump',
    'Flaring' : 'Flaring',
    'Gas dehydration' : 'GasDehydration',
    'Gas distribution' : 'GasDistribution',
    'Gas flooding compressor' : 'GasFloodingCompressor',
    'Gas gathering' : 'GasGathering',
    'Gas lifting compressor' : 'GasLiftingCompressor',
    'Gas storage wells' : 'GasStorageWells',
    # 'Gas transmission' : '',
    # 'HC gas reinjection compressor' : '',
    'Heavy oil dilution' : 'HeavyOilDilution',
    'Heavy oil upgrading' : 'HeavyOilUpgrading',
    'Liquefaction' : 'LNGLiquefaction',
    # 'Makeup water treatment' : '',
    # 'Makeup watter treatment' : '', # SPELLING ERROR
    'Mining' : 'BitumentMining',
    # 'Petcoke handling and storage' : '',
    'Post-storage compressor' : 'PostStorageCompressor',
    'Pre-membrane compressor' : 'PreMembraneCompressor',
    # 'Produced water treatment' : '',
    # 'Regasification' : '',
    'Ryan-Holmes unit' : 'RyanHolmes',
    'Separation' : 'Separation',
    'Sour gas reinjection compressor' : 'SourGasReinjectionCompressor',
    'Steam generation' : 'SteamGeneration',
    # 'Steam injection' : '',
    'Storage compressor' : 'StorageCompressor',
    'Storage separator' : 'StorageSeparator',
    # 'Transport' : '',
    'VRU compressor' : 'VRUCompressor',
    'Venting' : 'Venting',
    'Water injection' : 'WaterInjection',
}


DefaultCount = 0
DefaultFractionalDiff = 0.01

class ComparisonStatus(Enum):
    GOOD = 0,
    PROCESS_MISMATCH = 1,
    FIELD_MISMATCH = 2,
    VALUE_MISMATCH = 3


# Functionality moved to function to facilitate testing
def compare(file1, file2, count=DefaultCount, max_diff=DefaultFractionalDiff, verbose=False):
    import pandas as pd

    def read_results(filename):
        df = pd.read_csv(filename, index_col='process')
        df = df.rename(index=process_translator).sort_index(axis='rows')
        return df

    df1 = read_results(file1)
    df2 = read_results(file2)

    def compare_sets(iter1, iter2, name):
        s1 = set(iter1)
        s2 = set(iter2)

        if len(iter1) != len(iter2) or s1 != s2:
            print(f"{name} lists in the two result files differ")
            if verbose:
                extra1 = s1 - s2
                extra2 = s2 - s1
                if extra1:
                    print(f"   file1 has items not in file2: {extra1}")
                if extra2:
                    print(f"   file2 has items not in file1: {extra2}")

            return False

        return True

    #
    # First, check that both files list the same set of processes
    #
    if not compare_sets(df1.index, df2.index, "Process"):
        return ComparisonStatus.PROCESS_MISMATCH

    #
    # Next, check that the field names match
    #
    if count:
        # limit comparison to the first "count" fields
        df1 = df1[df1.columns[:count]]
        df2 = df2[df2.columns[:count]]

    # Check that the files contain the same fields
    if not compare_sets(df1.columns, df2.columns, "Field"):
        return ComparisonStatus.FIELD_MISMATCH

    #
    # Finally, check that the individual process values match, for each field.
    # More specifically, the total energy consumption value for each process in
    # a field must be within "max_diff" of the value in the baseline for the
    # same field and process. Report fields that differ, and if --verbose was
    # selected, report the actual value differences as well.
    #
    status = ComparisonStatus.GOOD

    for field, values1 in df1.iteritems():
        values2 = df2[field]

        na1 = values1.isna()
        na2 = values2.isna()
        comp = (na1 == na2)
        if not comp.all():
            status = ComparisonStatus.VALUE_MISMATCH
            print(f"Field '{field}' has NA values in different locations in the two files")
            if verbose:
                na_procs1 = list(values1.index[na1])
                na_procs2 = list(values2.index[na2])
                print(f"   file1 has NA values for processes {na_procs1}")
                print(f"   file2 has NA values for processes {na_procs2}")
            continue

        diffs = abs((values2 - values1) / values1)
        mismatches = diffs > max_diff
        if mismatches.any():
            status = ComparisonStatus.VALUE_MISMATCH
            print(f"Field {field} values differ")
            if verbose:
                print(f"   file1 has {values1[mismatches].to_string(header=False)}")
                print(f"   file2 has {values2[mismatches].to_string(header=False)}")

        if verbose and status == ComparisonStatus.GOOD:
            print(f"Field '{field}' matches")

    return status

class CompareCommand(SubcommandABC):
    def __init__(self, subparsers):
        kwargs = {'help' : '''Compare result CSV files''',
                  'description' : '''Compare CSV files with fields in columns and processes in row,
                      with the value either blank for disabled processes, or the total energy use per
                      day by process, after running the model. Mainly used for testing against OPGEEv3.
                      Note that CSV files for comparison can be generated using
                      "opg run --comparisonCSV filename".'''}

        super().__init__('compare', subparsers, kwargs)

    def addArgs(self, parser):
        '''
        Process the command-line arguments for this sub-command
        '''
        parser.add_argument('file1',
                            help='''A CSV file containing results for comparison against "file2"''')

        parser.add_argument('file2',
                            help='''A CSV file containing results for comparison against "file1"''')

        parser.add_argument('-n', '--count', type=int, default=DefaultCount,
                            help=f'''The number of fields to compare. Default is {DefaultCount}, which 
                                means compare all fields.''')

        parser.add_argument('-m', '--max-diff', type=float, default=DefaultFractionalDiff,
                            help=f'''The maximum (fractional) difference in values for "file2" 
                                relative to "file1" that are deemed "approximately the same". 
                                Default is {DefaultFractionalDiff}, 
                                i.e., (file2_value - file1_value) / file1_value <= {DefaultFractionalDiff}''')

        parser.add_argument('-v', '--verbose', action='store_true',
                            help='''Report all value differences. By default, only field differences 
                                are reported.''')

        return parser

    def run(self, args, tool):
        compare(args.file1, args.file2, args.count, args.max_diff, args.verbose)


# An alternative to naming the class 'Plugin' is to assign the class to PluginClass
PluginClass = CompareCommand
