## ----VERSION ONE-----------------------------------------------------------------
# Load Emme Modeller
_m = inro.modeller
import csv

# Load Scenario
scenario_number = 2
scenario = _m.Modeller().emmebank.scenario(scenario_number)

# Get network from scenario
network = scenario.get_network()

# Load transit segments and regular nodes
transit_segments = network.transit_segments()
regular_nodes = network.regular_nodes()

# Open file and read containing desired node ids, descriptions(station names)
with open("inputs.csv", "r") as input_file:
    csv_input_file = csv.reader(input_file)
    node_dict = {}
    for lines in csv_input_file:
        node_id = lines[0]
        if node_id == "id":
            continue
        description = lines[1]
        node_dict[node_id] = [description]
    board_alight_dict = {}
    for node in regular_nodes:
        if node["@stop"] >= 1:
            out_segments = node.outgoing_segments(include_hidden=True)
            boardings = 0
            alightings = 0
            for segment in out_segments:
                trans_boarding = segment.transit_boardings
                boardings += trans_boarding
                alightings += segment["@alightings"]
            rows = [boardings, alightings]
            board_alight_dict[node.id] = rows
    with open("outputs.csv", "w", newline="") as output_file:
        fields = ["node_id", "station", "boardings", "alightings"]
        csv_file_writer = csv.writer(output_file)
        csv_file_writer.writerow(fields)
        boarding_alighting_dict = dict(
            [(k, board_alight_dict[k] + node_dict[k]) for k in set(node_dict)]
        )
        for key in boarding_alighting_dict:
            rows = [
                key,
                boarding_alighting_dict[key][0],
                boarding_alighting_dict[key][1],
                str(boarding_alighting_dict[key][2]),
            ]
            csv_file_writer.writerow(rows)
