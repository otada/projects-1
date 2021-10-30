class CsharpCodeWriter():
    COLON = ':'
    COMMA = ','
    SEMI_COLON = ';'
    NEW_LINE = '\n'
    
    parameters_dict = {}
    value_list = []
    key_list = []
    
    
    parameter_name = ""
    index_number = ""
    function_type = ""
    function_name = ""
    module_name = ""
    default_value = ""

        
    def create_xtmf2_csharp_parameters(self, parameter_name, default_value, description_name,index_number, function_type, function_name):
        xtmf2_csharp_param = (
            '[Parameter(Name = "'
            + parameter_name
            + '", '
            + 'DefaultValue = "'
            + default_value
            +  '", '
            + 'Description = "'
            + description_name
            + '", '
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


    def create_xtmf2_csharp_modules(self, function_type, module_name, function_name):
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


    def create_xtmf2_unit_test_modules(self, function_type, module_name, default_value):
        writer_type = ""

        if function_type == "bool":
            writer_type = (
                'writer.WriteBoolean("'
                + str(module_name)
                + '", '
                + str(default_value).lower()
                + ");"
            )
        elif function_type == "int":
            writer_type = (
                'writer.WriteNumber("'
                + str(module_name)
                + '", '
                + str(default_value).lower()
                + ");"
            )
        elif function_type == "float":
            writer_type = (
                'writer.WriteNumber("'
                + str(module_name)
                + '", '
                + str(default_value).lower()
                + ");"
            )
        else:
            writer_type = (
                'writer.WriteString("'
                + str(module_name)
                + '", \"'
                + str(default_value).lower()
                + "\");"
            )

        return writer_type

    def create_xtmf2_unit_test_parameters(self, parameter_name, default_value, function_type):
        if function_type == "string":
            writer_type = parameter_name + " = Helper.CreateParameter(\"" + default_value.lower() + "\"),"
        else:
            writer_type = parameter_name + " = Helper.CreateParameter(" + default_value.lower() + "),"
        return writer_type
    
    def _load_file(self, param_txt_file_name):
        with open(param_txt_file_name) as reader:
            # header = reader.readline()
            # cells = header.strip().split(self.NEW_LINE)
            
            for item in reader:
                items = item.split(self.NEW_LINE)[0].split(self.COMMA)
                keys = items[0]
                values = items[-len(items)+1:]
                
                self.parameters_dict[keys] = values
                
    def _write_file(self):
        #---['Scenario Number', 'int', '0', 'scenario_number', '1', '']
        for key,value in self.parameters_dict.items():
            parameter_name = self.parameter_name = value[0]
            index_number = self.index_number = value[2]
            function_type = self.function_type = value[1]
            function_name = self.function_name = key
            module_name = self.module_name = value[3]
            default_value = self.default_value = value[4]
            if len(value) == 6:
                description_name = self.description = value[5]
            else:
                description_name = self.description_name = "".join(value[5:len(value)-1])
                                                           
            XTMF2_parameter_unittest = self.create_xtmf2_unit_test_parameters(function_name, default_value, function_type)
            XTMF2_module_unittest = self.create_xtmf2_unit_test_modules(
                function_type, module_name, default_value
            )
            
            XTMF2_module = self.create_xtmf2_csharp_modules(function_type, module_name, function_name)
            XTMF2_parameters = self.create_xtmf2_csharp_parameters(
                parameter_name, default_value, description_name, index_number, function_type, function_name,
            )
                
            # print(XTMF2_module)
            # print(XTMF2_parameters)
            print(XTMF2_parameter_unittest)
            # print(XTMF2_module_unittest)
    
    def run(self, param_txt_file_name):
        
        self._load_file(param_txt_file_name)
        self._write_file()
