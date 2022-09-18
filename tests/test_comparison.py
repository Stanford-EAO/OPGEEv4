from io import StringIO
from opgee.built_ins.compare_plugin import compare, ComparisonStatus

results1 = """
process,field_1,field_2,foobar,bumble
Reservoir,0.5,0.65,0.7,0.5
DownholePump,1.2,1,2.1,0.9
GasLifting,4.2,3.5,4.1,3.9
Dehydration,2.1,1.4,2.4,0.84
"""

# Has extra process "Other"
results2 = """
process,field_1,field_2,foobar,bumble
Reservoir,0.5,0.65,0.7,0.5
DownholePump,1.2,1,2.2,0.905
GasLifting,4.2,3.5,4.1,3.9
Dehydration,2.1,1.4,2.4,0.84
Other,1.1,1.2,1.23,0.9
"""

# Copy of results1
results3 = """
process,field_1,field_2,foobar,bumble
Reservoir,0.5,0.65,0.7,0.5
DownholePump,1.2,1,2.1,0.9
GasLifting,4.2,3.5,4.1,3.9
Dehydration,2.1,1.4,2.4,0.84
"""

# Has different value for Dehydration in field "bumble"
results4 = """
process,field_1,field_2,foobar,bumble
Reservoir,0.5,0.65,0.7,0.5
DownholePump,1.2,1,2.1,0.9
GasLifting,4.2,3.5,4.1,3.9
Dehydration,2.1,1.4,2.4,0.70
"""

# Has NA (missing value) in GasLifting for field_2
results5 = """
process,field_1,field_2,foobar,bumble
Reservoir,0.5,0.65,0.7,0.5
DownholePump,1.2,1,2.1,0.9
GasLifting,4.2,,4.1,3.9
Dehydration,2.1,1.4,2.4,0.84
"""

# Has "field_3" in place of "foobar"
results6 = """
process,field_1,field_2,field_3,bumble
Reservoir,0.5,0.65,0.7,0.5
DownholePump,1.2,1,2.1,0.9
GasLifting,4.2,,4.1,3.9
Dehydration,2.1,1.4,2.4,0.7
"""


def test_comparison1():
    # Test mismatched processes
    status = compare(StringIO(results1), StringIO(results2))
    assert status == ComparisonStatus.PROCESS_MISMATCH

def test_comparison2():
    # Test matching files
    status = compare(StringIO(results1), StringIO(results3))
    assert status == ComparisonStatus.GOOD

def test_comparison3():
    # Test divergent values
    status = compare(StringIO(results1), StringIO(results4))
    assert status == ComparisonStatus.VALUE_MISMATCH

def test_comparison4():
    # Test NA in one file not in the other
    status = compare(StringIO(results1), StringIO(results5))
    assert status == ComparisonStatus.VALUE_MISMATCH

def test_comparison5():
    # Test mismatched fields
    status = compare(StringIO(results1), StringIO(results6))
    assert status == ComparisonStatus.FIELD_MISMATCH

