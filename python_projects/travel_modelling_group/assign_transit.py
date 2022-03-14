def _surface_transit_speed_update(
    self, parameters, network, lambdaK, stsu_att, models, final
):
    if "transit_alightings" not in network.attributes("TRANSIT_SEGMENT"):
        network.create_attribute("TRANSIT_SEGMENT", "transit_alightings", 0.0)
    for line in network.transit_lines():
        prev_volume = 0.0
        headway = line.headway
        number_of_trips = parameters["assignment_period"] * 60.0 / headway

        # Get the STSU model to use
        if line[str(stsu_att.id)] != 0.0:
            model = models[int(line[str(stsu_att.id)]) - 1]
        else:
            continue

        boarding_duration = model["boarding_duration"]
        alighting_duration = model["alighting_duration"]
        default_duration = model["default_duration"]
        correlation = model["correlation"]
        mode_filter = model["mode_filter"]

        try:
            doors = segment.line["@doors"]
            if doors == 0.0:
                number_of_door_pairs = 1.0
            else:
                number_of_door_pairs = doors / 2.0
        except:
            number_of_door_pairs = 1.0

        for segment in line.segments(include_hidden=True):
            segment_number = segment.number
            if segment_number > 0 and segment.j_node is not None:
                segment.transit_alightings = max(
                    prev_volume + segment.transit_boardings - segment.transit_volume,
                    0.0,
                )
            else:
                continue
            # prevVolume is used above for the previous segments volume, the first segment is always ignored.
            prev_volume = segment.transit_volume

            boarding = (
                segment.transit_boardings / number_of_trips / number_of_door_pairs
            )
            alighting = (
                segment.transit_alightings / number_of_trips / number_of_door_pairs
            )

            old_dwell = segment.dwell_time
            segment_dwell_time = (
                (boarding_duration * boarding)
                + (alighting_duration * alighting)
                + (segment["@tstop"] * default_duration)
            )  # seconds
            segment_dwell_time /= 60  # minutes
            if segment_dwell_time >= 99.99:
                segment_dwell_time = 99.98

            alpha = 1 - lambdaK
            segment.dwell_time = old_dwell * alpha + segment_dwell_time * lambdaK
    data = network.get_attribute_values(
        "TRANSIT_SEGMENT", ["dwell_time", "transit_time_func"]
    )
    self.Scenario.set_attribute_values(
        "TRANSIT_SEGMENT", ["dwell_time", "transit_time_func"], data
    )
    return network


# ELSE STATMENT
for iteration in range(0, parameters["iterations"]):
    for i, tc in enumerate(parameters["transit_classes"]):
        spec_uncongested = self._get_base_assignment_spec_uncongested(
            scenario,
            tc["board_penalty_perception"],
            self.connector_logit_truncation,
            self.consider_total_impedance,
            demand_matrix_list[i],
            effective_headway_attribute_list[i],
            tc["fare_perception"],
            headway_fraction_attribute_list[i],
            impedance_matrix_list[i],
            tc["link_fare_attribute_id"],
            [tc["mode"]],
            parameters["node_logit_scale"],
            self.number_of_processors,
            parameters["origin_distribution_logit_scale"],
            tc["segment_fare_attribute"],
            self.use_logit_connector_choice,
            tc["wait_time_perception"],
            parameters["walk_all_way_flag"],
            walk_time_perception_attribute_list[i],
        )
        self._tracker.run_tool(
            extended_assignment_tool,
            specification=spec_uncongested,
            class_name=tc["name"],
            scenario=scenario,
            add_volumes=(i != 0),
        )
    network = scenario.get_network()
    network = self._surface_transit_speed_update(network, 1, stsu_att, True)
