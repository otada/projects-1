#
#
# TODO: ---Improve code to work for all parameters needed by emme tools
# ---1: change to class
# ---2: receive parameters from a txt or csv file
# ---3: handle error
# ---4:


first = """scenario_number
mode_list
demand_string
times_matrix_id
cost_matrix_id
tolls_matrix_id
peak_hour_factor
link_cost
toll_weight
iterations
r_gap
br_gap
norm_gap
performance_flag
run_title
link_toll_attribute_id
name_string
result_attributes
analysis_attributes
analysis_attributes_matrix_id
aggregation_operator
lower_bound
upper_bound
path_selection
multiply_path_prop_by_demand
multiply_path_prop_by_value
background_transit"""

second = """
scenario_number
scenario
link_toll_attribute_id
times_matrix_id
cost_matrix_id
tolls_matrix_id
run_title
mode_list
demand_string
demand_list
peak_hour_factor
link_cost
toll_weight
iterations
r_gap
br_gap
norm_gap
performance_flag
sola_flag
name_string
result_attributes
analysis_attributes
analysis_attributes_matrix_id
aggregation_operator
lower_bound
upper_bound
path_selection
multiply_path_prop_by_demand
multiply_path_prop_by_value
background_transit
number_of_processors"""
# class_analysis_attributes
# class_analysis_attributes_matrix
# class_analysis_operators
# class_analysis_lower_bounds
# class_analysis_upper_bounds
# class_analysis_selectors
frist_list = []
# ---process for run_xtmf
# for items in first.split("\n"):
#     print("self." + items + " = " + 'parameters["' + items + '"]')


# first_list = first.split("\n")

# for items in first.split("\n"):
#     print("self." + items + ",")

a = ", ".join(first.split("\n"))
"scenario_number, mode_list, demand_string, times_matrix_id, cost_matrix_id, tolls_matrix_id, peak_hour_factor, link_cost, toll_weight, iterations, r_gap, br_gap, norm_gap, performance_flag, run_title, link_toll_attribute_id, name_string, result_attributes, analysis_attributes, analysis_attributes_matrix_id, aggregation_operator, lower_bound, upper_bound, path_selection, multiply_path_prop_by_demand, multiply_path_prop_by_value, background_transit"

csharp_list_one = """ScenarioNumber
LinkTollAttributeId
TimesMatrixId
CostMatrixId
TollsMatrixId
RunTitle
ModeList 
DemandString
DemandList
PeakHourFactor
LinkCost
TollWeight
Iterations
rGap
brGap
normGap
PerformanceFlag
SOLAFlag
NameString
ResultAttributes
AnalysisAttributes
AnalysisAttributesMatrixId
AggregationOperator
LowerBound
UpperBound
PathSelection
MultiplyPathPropByDemand
MultiplyPathPropByValue
BackgroundTransit"""

# ---
parameter_values = """ScenarioNumber;int;0;scenario_number;1;
LinkTollAttributeId;string;1;link_toll_attribute_id;"@toll";
TimesMatrixId;int;2;times_matrix_id;0;
CostMatrixId;int;3;cost_matrix_id;0;
TollsMatrixId;int;4;tolls_matrix_id;0;
RunTitle;string;5;run_title;"multi-classrun";
ModeList;string;6;mode_list;"c";
DemandString;string;7;demand_string;"mf10,mf11,f12";
DemandList;string;8;demand_list;"mf10,mf11,f12";
PeakHourFactor;float;9;peak_hour_factor;0.43f;
LinkCost;int;10;link_cost;0;
TollWeight;int;11;toll_weight;0;
Iterations;int;12;iterations;100;
rGap;float;13;r_gap;0;
brGap;float;14;br_gap;0.1f;
normGap;float;15;norm_gap;0.05f;
PerformanceFlag;bool;16;performance_flag;false;
SOLAFlag;bool;17;sola_flag;true;
NameString;bool;18;name_string;true;
ResultAttributes;string;19;result_attributes;"";
AnalysisAttributes;string;20;analysis_attributes;"";
AnalysisAttributesMatrixId;int;21;analysis_attributes_matrix_id;0;
AggregationOperator;string;22;aggregation_operator;"+";
LowerBound;string;23;lower_bound;"none";
UpperBound;string;24;upper_bound;"";
PathSelection;string;25;path_selection;"";
MultiplyPathPropByDemand;bool;26;multiply_path_prop_by_demand;true;
MultiplyPathPropByValue;bool;27;multiply_path_prop_by_value;true;
BackgroundTransit;bool;28;background_transit;true;"""

parameter_keys = """Scenario Number
Link Toll Attribute Id
Times Matrix Id
Cost Matrix Id
Tolls Matrix Id
Run Title
Mode List 
Demand String
Demand List
Peak Hour Factor
Link Cost
Toll Weight
Iterations
r Gap
br Gap
norm Gap
Performance Flag
SOLA Flag
Name String
Result Attributes
Analysis Attributes
Analysis Attributes Matrix Id
Aggregation Operator
Lower Bound
Upper Bound
Path Selection
Multiply Path Prop By Demand
Multiply Path Prop By Value
Background Transit"""


def xtmf2_csharp_parameters(parameter_name, index_number, function_type, function_name):
    xtmf2_csharp_param = (
        '[Parameter(Name = "'
        + parameter_name
        + '", '
        + 'Description = "", '
        + "\n\t"
        + "Index = "
        + index_number
        + " )]"
        + "\n"
        + "public IFunction<"
        + function_type
        + "> "
        + function_name
        + ";"
        + "\n"
    )
    return xtmf2_csharp_param


def create_xtmf2_modules(function_type, module_name, function_name):
    writer_type = ""

    if function_type == "bool":
        writer_type = (
            'writer.WriteBoolean("'
            + str(module_name)
            + '", '
            + str(function_name)
            + ".Invoke());"
        )
    elif function_type == "int":
        writer_type = (
            'writer.WriteNumber("'
            + str(module_name)
            + '", '
            + str(function_name)
            + ".Invoke());"
        )
    elif function_type == "float":
        writer_type = (
            'writer.WriteNumber("'
            + str(module_name)
            + '", '
            + str(function_name)
            + ".Invoke());"
        )
    else:  # writer.WriteNumber("", ScenarioNumber.Invoke());
        writer_type = (
            'writer.WriteString("'
            + str(module_name)
            + '", '
            + str(function_name)
            + ".Invoke());"
        )

    return writer_type


def create_xtmf2_unit_test_modules(function_type, module_name, default_value):
    writer_type = ""

    if function_type == "bool":
        writer_type = (
            'writer.WriteBoolean("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )
    elif function_type == "int":
        writer_type = (
            'writer.WriteNumber("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )
    elif function_type == "float":
        writer_type = (
            'writer.WriteNumber("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )
    else:
        writer_type = (
            'writer.WriteString("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )

    return writer_type


def create_xtmf2_unit_test_parameters(function_type, module_name, default_value):
    writer_type = ""

    if function_type == "bool":
        writer_type = (
            'writer.WriteBoolean("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )
    elif function_type == "int":
        writer_type = (
            'writer.WriteNumber("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )
    elif function_type == "float":
        writer_type = (
            'writer.WriteNumber("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )
    else:
        writer_type = (
            'writer.WriteString("'
            + str(module_name)
            + '", '
            + str(default_value)
            + ");"
        )

    return writer_type


def create_xtmf2_unit_test_module(parameter_name, default_value):
    writer_type = parameter_name + " = Helper.CreateParameter(" + default_value + "),"
    return writer_type


parameters_dict = {}
value_list = []
key_list = []

# ---Add file values to key and value list
for keys in parameter_keys.split("\n"):
    key_list.append(keys)

for values in parameter_values.split("\n"):
    value_list.append(values.split(";"))

# --- Create dictionary with keys and values
i = 0
while i < len(key_list):
    parameters_dict[key_list[i]] = value_list[i]
    i += 1

# ---create c# xtmf2 parametes [ScenarioNumber;string;0;scenario_number]
def write_xtmf2_parameters():
    for key, value in parameters_dict.items():
        parameter_name = key
        index_number = value[2]
        function_type = value[1]
        function_name = value[0]
        XTMF2_parameters = xtmf2_csharp_parameters(
            parameter_name, index_number, function_type, function_name
        )
        print(XTMF2_parameters)


def write_xtmf2_modules():
    for key, value in parameters_dict.items():
        function_type = value[1]
        function_name = value[0]
        module_name = value[3]
        XTMF2_module = create_xtmf2_modules(function_type, module_name, function_name)
        print(XTMF2_module)


def write_xtmf2_unit_test_modules():
    for value in parameters_dict.values():
        function_type = value[1]
        module_name = value[3]
        if len(value) < 5:
            default_value = ""
        else:
            default_value = value[4].lower()
        XTMF2_module = create_xtmf2_unit_test_modules(
            function_type, module_name, default_value
        )
        print(XTMF2_module)


def write_xtmf2_unit_test_parameters():
    for value in parameters_dict.values():
        parameter_name = value[0]
        if len(value) < 5:
            default_value = ""
        else:
            default_value = value[4].lower()
        XTMF2_parameter = create_xtmf2_unit_test_module(parameter_name, default_value)
        print(XTMF2_parameter)


# write_xtmf2_parameters()
# write_xtmf2_modules()
# write_xtmf2_unit_test_modules()
# write_xtmf2_unit_test_parameters()
