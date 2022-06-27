#---LICENSE----------------------
'''
    Copyright 2015 Travel Modelling Group, Department of Civil Engineering, University of Toronto

    This file is part of the TMG Toolbox.

    The TMG Toolbox is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    The TMG Toolbox is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with the TMG Toolbox.  If not, see <http://www.gnu.org/licenses/>.
'''
#---METADATA---------------------
'''
Fare-Based Transit Network (FBTN) From Schema

    Authors: pkucirek

    Latest revision by: mattaustin222
    
    
    [Description]
        
'''
#---VERSION HISTORY
'''
    0.0.1 Created on 2014-03-09 by pkucirek
    
    1.0.0 Debugged and deployed by 2014-05-23
    
    1.1.0 Added feature to save base I-node IDs for transit segments
        as they are being moved over to the hyper network. This enables
        transit speed updating.
    
    1.1.1 Fixed a bug in PrepareNetwork which only considers segments that permit alightings as 
        'stops.' We want to catch both boardings AND alightings
    
    1.1.2 Slightly tweaked the page() function's Javascript to allow the NONE option when segment
        attributes are pre-loaded from scenario.
        
    1.1.3 Slightly tweaked to over-write the FBTN scenario if it already exists.
    
    1.1.4 Fixed a bug in the scenario overwrite: If the target (new) scenario already exists,
        it gets deleted, then the base scenario is copied in its place first. This ensures that
        the new scenario is a verbatim copy of the base scenario prior to publishing the network.
        Before, it was possible to end up with different extra attributes between the two 
        scenarios.
        
    1.1.5 Modified to use the new spatial index. Also changed the copy scenario call to NOT
        copy over strategy or path files as this considerably increases runtime.
    
    1.2.0 Added new feature to accept relative paths for shapefiles. Absolute paths are still
        supported.
    
    1.3.0 Added new feature to associate a set of station zones with line group. Initial boarding rules
        will then be applied to all centroid connectors going from station zones to a stop of that
        operator.
        
    1.3.1 Minor change to accept two station groups being associated with a shared line group

    1.4.0 Added option to allow station-to-centroid hypernetwork connections by default. This 
        enables the proper connection of a centroid to a multi-operator station. The station group
        method allows for finer control of centroids, but cannot handle multiple operators at 
        a station. 
    
'''
from copy import copy
from contextlib import contextmanager
from contextlib import nested
from html import HTML
from itertools import combinations as get_combinations
from os import path
import traceback as _traceback
from xml.etree import ElementTree as _ET
import json
from json import loads as _parsedict

import inro.modeller as _m
from inro.emme.core.exception import ModuleError

_MODELLER = _m.Modeller() #Instantiate Modeller once.
_util = _MODELLER.module('tmg.common.utilities')
_tmgTPB = _MODELLER.module('tmg.common.TMG_tool_page_builder')
_geolib = _MODELLER.module('tmg.common.geometry')
_editing = _MODELLER.module('tmg.common.network_editing')
_spindex = _MODELLER.module('tmg.common.spatial_index')
Shapely2ESRI = _geolib.Shapely2ESRI
GridIndex = _spindex.GridIndex
TransitLineProxy = _editing.TransitLineProxy
NullPointerException = _util.NullPointerException
EMME_VERSION = _util.getEmmeVersion(tuple) 

##########################################################################################################    

class XmlValidationError(Exception):
    pass

class grid():
    '''
    Grid class to support tuple indexing (just for coding convenience).
    
    Upon construction, it copies the default value into each of its cells.
    '''
    
    def __init__(self, x_size, y_size, default= None):
        x_size, y_size = int(x_size), int(y_size)
        self._data = []
        self.x = x_size
        self.y = y_size
        i = 0
        total = x_size * y_size
        while i < total:
            self._data.append(copy(default))
            i += 1
    
    def __getitem__(self, key):
        x,y = key
        x, y = int(x), int(y)
        index = x * self.y + y
        return self._data[index]
    
    def __setitem__(self, key, val):
        x,y = key
        x, y = int(x), int(y)
        index = x * self.y + y
        self._data[index] = val

class NodeSpatialProxy():
    def __init__(self, id, x, y):
        self.id = id
        self.x = x
        self.y = y
        self.zone = 0
        self.geometry = _geolib.Point(x,y)
    
    def __str__(self):
        return str(self.id)
        

#---
#---MAIN MODELLER TOOL--------------------------------------------------------------------------------

class FBTNFromSchemaMulticlass(_m.Tool()):
    
    version = '0.0.1'
    tool_run_msg = ""
    number_of_tasks = 5 # For progress reporting, enter the integer number of tasks here
    
    # Tool Input Parameters
    #    Only those parameters neccessary for Modeller and/or XTMF to dock with
    #    need to be placed here. Internal parameters (such as lists and dicts)
    #    get intitialized during construction (__init__)
    
    XMLBaseSchemaFile = _m.Attribute(str)
    XMLFareRules = _m.Attribute(str)
    VirtualNodeDomain = _m.Attribute(int)
    
    xtmf_BaseScenarioNumber = _m.Attribute(int) # parameter used by XTMF only
    BaseScenario = _m.Attribute(_m.InstanceType) # common variable or parameter
    NewScenarioNumber = _m.Attribute(int)
    NewScenarioTitle = _m.Attribute(str)
    
    TransferModeId = _m.Attribute(str) 
    SegmentFareAttributeId = _m.Attribute(str)
    link_fare_attributeId = _m.Attribute(str)
    SegmentINodeAttributeId = _m.Attribute(str)

    StationConnectorFlag = _m.Attribute(bool)
    
    __ZONE_TYPES = ['node_selection', 'from_shapefile']
    __RULE_TYPES = ['initial_boarding', 
                    'transfer',
                    'in_vehicle_distance',
                    'zone_crossing']
    __BOOL_PARSER = {'TRUE': True, 'T': True, 'FALSE': False, 'F': False}
    
    def __init__(self):
        #---Init internal variables
        self._tracker = _util.ProgressTracker(self.number_of_tasks) #init the ProgressTracker
        
        #---Set the defaults of parameters used by Modeller
        self.BaseScenario = _MODELLER.scenario #Default is primary scenario
        self.VirtualNodeDomain = 100000
        self.NewScenarioTitle = ""
        
        #self.link_fare_attributeId = "@lfare"
        #self.SegmentFareAttributeId = "@sfare"

        self.StationConnectorFlag = True
    
    def page(self):
        pb = _tmgTPB.TmgToolPageBuilder(self, title="FBTN From Schema v%s" %self.version,
                     description="Generates a hyper-network to support fare-based transit \
                     assignment (FBTA), from an XML schema file. Links and segments with negative\
                     fare values will be reported to the Logbook for further inspection. \
                     For fare schema specification, \
                     please consult TMG documentation.\
                     <br><br><b>Temporary storage requirements:</b> one transit line extra \
                     attribute, one node extra attribute.\
                     <br><br><em>Not Callable from Modeller. Please use XTMF</em>",
                     branding_text="- TMG Toolbox")
        
        '''if self.tool_run_msg != "": # to display messages in the page
            pb.tool_run_status(self.tool_run_msg_status)
        
        pb.add_select_file(tool_attribute_name='XMLSchemaFile', window_type='file',
                           file_filter="*.xml", title="Fare Schema File")
        
        pb.add_header("SCENARIO")
        
        pb.add_select_scenario(tool_attribute_name='BaseScenario',
                               title='Scenario:',
                               allow_none=False)
        
        pb.add_new_scenario_select(tool_attribute_name='NewScenarioNumber',
                                   title="New Scenario Id")
        
        pb.add_text_box(tool_attribute_name='NewScenarioTitle',
                        title= "New Scenario Title", size=60)
        
        pb.add_header("OPTIONS AND RESULTS")
        
        pb.add_text_box(tool_attribute_name= 'VirtualNodeDomain', size=10,
                        title= "Virtual Node Domain",
                        note= "All virtual node IDs created will be greater than \
                        this number.")
        
        keyval1 = []
        for id, type, description in _util.getScenarioModes(self.BaseScenario, ['AUX_TRANSIT']):
            val = "%s - %s" %(id, description)
            keyval1.append((id, val))
        
        pb.add_select(tool_attribute_name='TransferModeId', keyvalues= keyval1,
                      title="Transfer Mode", 
                      note="Select an AUX_TRANSIT mode to apply to virtual connector links.")
        
        keyval2 = []
        keyval3 = []
        keyval4 = [(-1, "None - Do not save segment base info")]
        for exatt in self.BaseScenario.extra_attributes():
            if exatt.type == 'LINK':
                val = "%s - %s" %(exatt.name, exatt.description)
                keyval2.append((exatt.name, val))
            elif exatt.type == 'TRANSIT_SEGMENT':
                val = "%s - %s" %(exatt.name, exatt.description)
                keyval3.append((exatt.name, val))
                keyval4.append((exatt.name, val))
        
        pb.add_select(tool_attribute_name= 'link_fare_attributeId',
                      keyvalues= keyval2,
                      title= "Link Fare Attribute",
                      note= "Select a LINK extra attribute in which to save \
                      transit fares")
        
        pb.add_select(tool_attribute_name= 'SegmentFareAttributeId',
                      keyvalues= keyval3,
                      title="Segment Fare Attribute",
                      note= "Select a TRANSIT SEGMENT extra attribute in which \
                      to save transit fares.")
        
        pb.add_select(tool_attribute_name= 'SegmentINodeAttributeId',
                      keyvalues= keyval4,
                      title= "Segment I-node Attribute",
                      note= "Select a TRANSIT SEGMENT extra attribute in which \
                      to save the base node ID. This data is used to implement \
                      transit speed updating. Select 'None' to disable this \
                      feature.")
        
        pb.add_checkbox(tool_attribute_name= 'StationConnectorFlag',
                        label= "Allow station-to-centroid connections?")                      
        
        #---JAVASCRIPT
        pb.add_html("""
<script type="text/javascript">
    $(document).ready( function ()
    {
        var tool = new inro.modeller.util.Proxy(%s) ;
        $("#BaseScenario").bind('change', function()
        {
            $(this).commit();
            
            $("#TransferModeId")
                .empty()
                .append(tool.preload_auxtr_modes())
            inro.modeller.page.preload("#TransferModeId");
            $("#TransferModeId").trigger('change')
            
            $("#link_fare_attributeId")
                .empty()
                .append(tool.preload_scenario_link_attributes())
            inro.modeller.page.preload("#link_fare_attributeId");
            $("#link_fare_attributeId").trigger('change')
            
            $("#SegmentFareAttributeId")
                .empty()
                .append(tool.preload_scenario_segment_attributes())
            inro.modeller.page.preload("#SegmentFareAttributeId");
            $("#SegmentFareAttributeId").trigger('change')
            
            $("#SegmentINodeAttributeId")
                .empty()
                .append("<option value='-1'>None - Do not save segment base info</option>")
                .append(tool.preload_scenario_segment_attributes())
            inro.modeller.page.preload("#SegmentINodeAttributeId");
            $("#SegmentINodeAttributeId").trigger('change')
        });
    });
</script>""" % pb.tool_proxy_tag)'''
        
        return pb.render()
    
    ##########################################################################################################
        
    def run(self):
        self.tool_run_msg = ""
        self._tracker.reset()
        
        if not self.XMLSchemaFile: raise NullPointerException("Fare Schema file not specified")
        if not self.VirtualNodeDomain: raise NullPointerException("Virtual Node Domain not specified")
        if not self.link_fare_attributeId: raise NullPointerException("Link fare attribute not specified")
        if not self.SegmentFareAttributeId: raise NullPointerException("Segment fare attribute not specified")
        
        try:
            self._Execute()
        except Exception as e:
            self.tool_run_msg = _m.PageBuilder.format_exception(
                e, _traceback.format_exc())
            raise
        
        self.tool_run_msg = _m.PageBuilder.format_info("Done.")
    
    
    @_m.method(return_type= bool)
    def check_415(self):
        if EMME_VERSION >= (4,1,5):
            return True
        return False
        
    def __call__(self, XMLBaseSchemaFile, xtmf_BaseScenarioNumber, NewScenarioNumber,
                 TransferModeId, VirtualNodeDomain, StationConnectorFlag, XMLFareRules):
        
        #---1 Set up scenario
        self.BaseScenario = _MODELLER.emmebank.scenario(xtmf_BaseScenarioNumber)
        if (self.BaseScenario is None):
            raise Exception("Base scenario %s was not found!" %xtmf_BaseScenarioNumber)
        XMLFareRulesJSON = json.loads(XMLFareRules.replace("\'","\"").replace("\\","/"))
        self.XMLFareRulesFile  = []
        self.SegmentFareAttributeId = []
        self.link_fare_attributeId = []
        FareClasses = XMLFareRulesJSON['FareClasses']
        for i in range(len(XMLFareRulesJSON['FareClasses'])):
            self.XMLFareRulesFile.append(FareClasses[i]['SchemaFile'])
            self.SegmentFareAttributeId.append(FareClasses[i]['segment_fare_attribute'])
            self.link_fare_attributeId.append(FareClasses[i]['link_fare_attribute'])
        for i in range(len(self.SegmentFareAttributeId)):
            if self.BaseScenario.extra_attribute(self.SegmentFareAttributeId[i]) is None:
                att = self.BaseScenario.create_extra_attribute('TRANSIT_SEGMENT',
                                                           self.SegmentFareAttributeId[i])
                att.description = "SEGMENT transit fare"
                _write("Created segment fare attribute %s" %self.SegmentFareAttributeId[i])
            
        for i in range(len(self.link_fare_attributeId)):
            if self.BaseScenario.extra_attribute(self.link_fare_attributeId[i]) is None:
                att = self.BaseScenario.create_extra_attribute('LINK',
                                                           self.link_fare_attributeId[i])
                att.description = "LINK transit fare"
                _write("Created link fare attribute %s" %self.link_fare_attributeId[i])
        
        self.XMLBaseSchemaFile = XMLBaseSchemaFile
        self.NewScenarioNumber = NewScenarioNumber
        self.NewScenarioTitle = self.BaseScenario.title + " - FBTN"
        self.TransferModeId = TransferModeId
        self.VirtualNodeDomain = VirtualNodeDomain
        self.StationConnectorFlag = StationConnectorFlag
        
        try:
            self._Execute()
        except Exception as e:
            msg = str(e) + "\n" + _traceback.format_exc()
            raise Exception(msg)
    
    ##########################################################################################################    
    
    
    def _Execute(self):
        with _trace(name="{classname} v{version}".format(classname=(self.__class__.__name__), version=self.version),
                                     attributes=self._GetAtts()):
            
            self._nextNodeId = self.VirtualNodeDomain
            
            rootBase = _ET.parse(self.XMLBaseSchemaFile).getroot()            
            
            #Validate the XML Schema File
            nGroups, nZones, nStationGroups = self._ValidateBaseSchemaFile(rootBase)
            n_rules = []
            rootFare = []
            for i in range(len(self.XMLFareRulesFile)):
                rootFare.append(_ET.parse(self.XMLFareRulesFile[i]).getroot())  
                n_rules.append(self._ValidateFareSchemaFile(rootFare[i]))
            n_rules = sum(n_rules)
            self._tracker.complete_task()
            
            #Load the line groups and zones
            version = rootBase.find('version').attrib['number']
            _write("Loading Base Schema File version %s" %version)
            print "Loading Base Schema File version %s" %version
            
            self._tracker.start_process(nGroups + nZones)
            with nested (_util.tempExtraAttributeMANAGER(self.BaseScenario, 'TRANSIT_LINE', description= "Line Group"),
                         _util.tempExtraAttributeMANAGER(self.BaseScenario, 'NODE', description= "Fare Zone")) \
                     as (lineGroupAtt, zoneAtt):
                
                with _trace("Transit Line Groups"):
                    groupsElement = rootBase.find('groups')
                    group_ids_2_int, int2group_ids = self._LoadGroups(groupsElement, lineGroupAtt.id)
                    print "Loaded groups."
                
                stationGroupsElement = rootBase.find('station_groups')
                if stationGroupsElement is not None:
                    with _trace("Station Groups"):
                        stationGroups = self._LoadStationGroups(stationGroupsElement)
                        print "Loaded station groups"
                
                zonesElement = rootBase.find('zones')
                if zonesElement is not None:
                    with _trace("Fare Zones"):
                        zone_id2Int, int2zone_id, nodeProxies = self._LoadZones(zonesElement, zoneAtt.id)
                        print "Loaded zones."
                else:
                    zone_id2Int, int2zone_id, nodeProxies = {}, {}, {}
                self._tracker.complete_task() #Complete the group/zone loading task
                
                #Load and prepare the network.
                self._tracker.start_process(2)
                network = self.BaseScenario.get_network()
                print "Loaded network."
                self._tracker.complete_subtask()
                self._PrepareNetwork(network, nodeProxies, lineGroupAtt.id)
                self._tracker.complete_task()
                print "Prepared base network."
            
            #Transform the network
            with _trace("Transforming hyper network"):
                transfer_grid, zone_crossing_grid = self._transform_network(network, nGroups, nZones)
                #print transfer_grid[0,1]
                if nStationGroups > 0:
                    self._index_station_connectors(network, transfer_grid, stationGroups, group_ids_2_int)
                print ("Hyper network generated.")
            
            #Apply fare rules to network.   
            with _trace("Applying fare rules"):
                self._tracker.start_process(n_rules + 1)
                for i in range(len(self.XMLFareRulesFile)):
                    fareRulesElement = rootFare[i].find('fare_rules')
                    self._apply_fare_rules(network, fareRulesElement, transfer_grid, zone_crossing_grid,
                                         group_ids_2_int, zone_id2Int, self.SegmentFareAttributeId[i], self.link_fare_attributeId[i])
                    self._Check_for_negative_fares(network, self.SegmentFareAttributeId[i], self.link_fare_attributeId[i])

                    self._tracker.complete_task()
            print "Applied fare rules to network."
            
            #Publish the network
            bank = _MODELLER.emmebank
            if bank.scenario(self.NewScenarioNumber) is not None:
                bank.delete_scenario(self.NewScenarioNumber)
            newSc = bank.copy_scenario(self.BaseScenario.id, self.NewScenarioNumber, \
                                       copy_path_files=False, copy_strat_files=False)
            newSc.title = self.NewScenarioTitle
            newSc.publish_network(network, resolve_attributes= True)
            
            _MODELLER.desktop.refresh_needed(True) #Tell the desktop app that a data refresh is required

    ##########################################################################################################     
    
    def _GetAtts(self):
        atts = {
                "Scenario" : str(self.BaseScenario),
                "Version": self.version, 
                "self": self.__MODELLER_NAMESPACE__}
            
        return atts
    
    #---
    #---SCHEMA LOADING-----------------------------------------------------------------------------------
    
    def _ValidateBaseSchemaFile(self, root):
        
        #Check the top-level of the file
        versionElem = root.find('version')
        if versionElem is None:
            raise XmlValidationError("Base schema must specify a 'version' element.")
        
        groupsElement = root.find('groups')
        if groupsElement is None:
            raise XmlValidationError("Base schema must specify a 'groups' element.")
        
        zonesElement = root.find('zones')
       
    
        #Validate version
        try:
            version = versionElem.attrib['number']
        except KeyError:
            raise XmlValidationError("Version element must specify a 'number' attribute.")
        
        #Validate groups
        groupElements = groupsElement.findall('group')
        self.validgroup_ids = set()
        if len(groupElements) == 0:
            raise XmlValidationError("Scehma must specify at least one group elements")
        for i, groupElement in enumerate(groupElements):
            if not 'id' in groupElement.attrib:
                raise XmlValidationError("Group element #%s must specify an 'id' attribute" %i)
            id = groupElement.attrib['id']
            if id in self.validgroup_ids:
                raise XmlValidationError("Group id '%s' found more than once. Each id must be unique." %id)
            self.validgroup_ids.add(id)
            
            selectionElements = groupElement.findall('selection')
            if len(selectionElements) == 0:
                raise XmlValidationError("Group element '%s' does not specify any 'selection' sub-elements" %id)
            
        #Validate zones, if required
        self.validzone_ids = set()
        if zonesElement is not None:
            shapeFileElements = zonesElement.findall('shapefile')
            zoneElements = zonesElement.findall('zone')
            
            shapeFileIds = set()
            for i, shapefileElement in enumerate(shapeFileElements):
                if not 'id' in shapefileElement.attrib:
                    raise XmlValidationError("Shapefile #%s element must specify an 'id' attribute" %i)
                
                id = shapefileElement.attrib['id']
                if id in shapeFileIds:
                    raise XmlValidationError("Shapefile id '%' found more than once. Each id must be unique" %id)
                shapeFileIds.add(id)
                
                if not 'path' in shapefileElement.attrib:
                    raise XmlValidationError("Sahpefile '%s' must specify a 'path' attribute" %id)
                p = shapefileElement.attrib['path']
                p = self._GetAbsoluteFilepath(p) #Joins the path if it is relative.
                
                if not path.exists(p):
                    raise XmlValidationError("File not found for id '%s' at %s" %(id, p))
            
            for i, zoneElement in enumerate(zoneElements):
                if not 'id' in zoneElement.attrib:
                    raise XmlValidationError("Zone element #%s must specify an 'id' attribute" %i)
                id = zoneElement.attrib['id']
                if id in self.validzone_ids:
                    raise XmlValidationError("Zone id '%s' found more than once. Each id must be unique" %id)
                self.validzone_ids.add(id)
                
                if not 'type' in zoneElement.attrib:
                    raise XmlValidationError("Zone '%s' must specify a 'type' attribute" %id)
                zoneType = zoneElement.attrib['type']
                if not zoneType in self.__ZONE_TYPES:
                    raise XmlValidationError("Zone type '%s' for zone '%s' is not recognized." %(zoneType, id))
                
                if zoneType == 'node_selection':
                    if len(zoneElement.findall('node_selector')) == 0:
                        raise XmlValidationError("Zone type 'node_selection' for zone '%s' must specify at least one 'node_selector' element." %id)
                elif zoneType == 'from_shapefile':
                    childElement = zoneElement.find('from_shapefile')
                    if childElement is None:
                        raise XmlValidationError("Zone type 'from_shapefile' for zone '%s' must specify exactly one 'from_shapefile' element." %id)
                    
                    if not 'id' in childElement.attrib:
                        raise XmlValidationError("from_shapefile element must specify an 'id' attribute.")
                    if not 'FID' in childElement.attrib:
                        raise XmlValidationError("from_shapefile element must specify a 'FID' attribute.")
                    
                    sid = childElement.attrib['id']
                    if not sid in shapeFileIds:
                        raise XmlValidationError("Could not find a shapefile with the id '%s' for zone '%s'." %(sid, id))
                    
                    try:
                        FID = int(childElement.attrib['FID'])
                        if FID < 0: raise Exception()
                    except:
                        raise XmlValidationError("FID attribute must be a positive integer.")
        else:
            zoneElements = []
        
        nStationGroups = 0
        stationGroupsElement = root.find('station_groups')
        if stationGroupsElement is not None:
            stationGroupElements = stationGroupsElement.findall('station_group')
            
            for element in stationGroupElements:
                forGroup = element.attrib['for']
                if not forGroup in self.validgroup_ids:
                    raise XmlValidationError("Could not find a group '%s' for to associate with a station group" %forGroup)
                nStationGroups += 1

        
        def checkgroup_id(group, name):
            if not group in self.validgroup_ids:
                raise XmlValidationError("Could not find a group with id '%s' for element '%s'" %(group, name))
            
        def checkzone_id(zone, name):
            if not zone in self.validzone_ids:
                raise XmlValidationError("Could not find a zone with id '%s' for element '%s'" %(zone, name))
            
        def checkIsBool(val, name):
            if not val.upper() in ['TRUE', 'T', 'FALSE', 'F']:
                raise XmlValidationError("Value '%s' for element '%s' must be True or False." %(val, name)) 
        
        return len(groupElements), len(zoneElements), nStationGroups

    def _ValidateFareSchemaFile(self, root):
        
        
        fareRulesElement = root.find('fare_rules')
        if fareRulesElement is None:
            raise XmlValidationError("Fare schema must specify a 'fare_rules' element.")


        fare_elements = fareRulesElement.findall('fare')
        
        def checkgroup_id(group, name):
            if not group in self.validgroup_ids:
                raise XmlValidationError("Could not find a group with id '%s' for element '%s'" %(group, name))
            
        def checkzone_id(zone, name):
            if not zone in self.validzone_ids:
                raise XmlValidationError("Could not find a zone with id '%s' for element '%s'" %(zone, name))
            
        def checkIsBool(val, name):
            if not val.upper() in ['TRUE', 'T', 'FALSE', 'F']:
                raise XmlValidationError("Value '%s' for element '%s' must be True or False." %(val, name)) 
        
        for i, fare_element in enumerate(fare_elements):
            if not 'cost' in fare_element.attrib:
                raise XmlValidationError("Fare element #%s must specify a 'cost' attribute" %i)
            if not 'type' in fare_element.attrib:
                raise XmlValidationError("Fare element #%s must specify a 'type' attribute" %i)
            
            try:
                cost = float(fare_element.attrib['cost'])
            except ValueError:
                raise XmlValidationError("Fare element #%s attribute 'cost' must be valid decimal number." %i)
            
            ruleType = fare_element.attrib['type']            
            if ruleType == 'initial_boarding':
                requiredChildren = {'group': checkgroup_id}
                optionalChildren = {'in_zone': checkzone_id,
                                    'include_all_groups': checkIsBool}
            elif ruleType == 'transfer':
                requiredChildren = {'from_group': checkgroup_id,
                                    'to_group': checkgroup_id}
                optionalChildren = {'bidirectional': checkIsBool}
            elif ruleType == 'zone_crossing':
                requiredChildren = {'group': checkgroup_id,
                                    'from_zone': checkzone_id,
                                    'to_zone': checkzone_id}
                optionalChildren = {'bidirectional': checkIsBool}
            elif ruleType == 'distance_in_vehicle':
                requiredChildren = {'group': checkgroup_id}
                optionalChildren = {}
            else:
                raise XmlValidationError("Fare rule type '%s' not recognized." %ruleType)
            
            #Check required children
            for name, checkFunc in requiredChildren.iteritems():
                child = fare_element.find(name)
                if child is None:
                    raise XmlValidationError("Fare element #%s of type '%s' must specify a '%s' element" %(i, ruleType, name))
                
                text = child.text
                checkFunc(text, name)
            
            #Check optional children
            for name, checkFunc in optionalChildren.iteritems():
                child = fare_element.find(name)
                if child is None: continue
                
                text = child.text
                checkFunc(text, name)
        
        return len(fare_elements)
    
    def _LoadGroups(self, groupsElement, lineGroupAttId):
        group_ids_2_int = {}
        int2group_ids ={}
        
        tool = _MODELLER.tool('inro.emme.network_calculation.network_calculator')
        def getSpec(number, selection):
            return {
                "result": lineGroupAttId,
                "expression": str(number),
                "aggregation": None,
                "selections": {
                    "transit_line": selection
                },
                "type": "NETWORK_CALCULATION"
            }
        
        for i, groupElement in enumerate(groupsElement.findall('group')):
            group_number = i + 1
            
            id = groupElement.attrib['id']
            group_ids_2_int[id] = group_number
            int2group_ids[group_number] = id
            
            for selectionElement in groupElement.findall('selection'):
                selector = selectionElement.text
                spec = getSpec(group_number, selector)
                try:
                    tool(spec, scenario= self.BaseScenario)
                except ModuleError:
                    msg = "Emme runtime error processing line group '%s'." %id
                    _write(msg)
                    print msg
            
            msg = "Loaded group %s: %s" %(group_number, id)
            print msg
            _write(msg)
            
            self._tracker.complete_subtask()
        
        return group_ids_2_int, int2group_ids
    
    def _LoadStationGroups(self, stationGroupsElement):
        tool = _MODELLER.tool('inro.emme.network_calculation.network_calculator')
        
        stationGroups, ids = {}, []
        with _util.tempExtraAttributeMANAGER(self.BaseScenario, 'NODE', returnId=True) as attr:
            
            for i, stationGroupElement in enumerate(stationGroupsElement.findall('station_group')):
                forGroup = stationGroupElement.attrib['for']
                selector =  stationGroupElement.attrib['selection']
                
                spec = {
                        "result": attr,
                        "expression": str(i + 1), #Plus one since the attribute is initialized to 0
                        "aggregation": None,
                        "selections": {
                            "node": selector
                        },
                        "type": "NETWORK_CALCULATION"
                    }
                tool(spec, scenario= self.BaseScenario)
                stationGroups[forGroup] = set()
                ids.append(forGroup)
            
            indices, table = self.BaseScenario.get_attribute_values('NODE', [attr])
            for nodeNumber, index in indices.iteritems():
                value = int(table[index])
                if value == 0: continue
                stationGroups[ids[value - 1]].add(nodeNumber)
        
        return stationGroups            
        
    
    def _LoadZones(self, zonesElement, zoneAttributeId):
        '''
        Loads node zone numbers. This is a convoluted process in order to allow
        users to apply zones by BOTH selectors AND geometry. The first method
        applies changes directly to the base scenario, which the second requires
        knowing the node coordindates to work. 
        
        Much of this method (and associated sub-methods) is BLACK MAGIC
        '''
        zone_id2Int = {}
        int2zone_id = {}
        
        tool = _MODELLER.tool('inro.emme.network_calculation.network_calculator')
        
        shapefiles = self._LoadShapefiles(zonesElement)
        spatialIndex, nodes = self._IndexNodeGeometries()
        
        try:
            for number, zoneElement in enumerate(zonesElement.findall('zone')):
                id = zoneElement.attrib['id']
                typ = zoneElement.attrib['type']
                
                number += 1
                
                zone_id2Int[id] = number
                int2zone_id[number] = id
                
                if typ == 'node_selection':
                    self._LoadZoneFromSelection(zoneElement, zoneAttributeId, tool, number, nodes)
                elif typ == 'from_shapefile':
                    self._LoadZoneFromGeometry(zoneElement, spatialIndex, shapefiles, number, nodes)
                
                msg = "Loaded zone %s: %s" %(number, id)
                _write(msg)
                print msg
                
                self._tracker.complete_subtask()
        finally: #Close the shapefile readers
            for reader in shapefiles.itervalues():
                reader.close()
        
        return zone_id2Int, int2zone_id, nodes
        
    
    def _LoadShapefiles(self, zonesElement):
        shapefiles = {}
        try:
            for shapefileElement in zonesElement.findall('shapefile'):
                id = shapefileElement.attrib['id']
                pth = shapefileElement.attrib['path']
                pth = self._GetAbsoluteFilepath(pth) #Join the path if it is relative
                
                reader = Shapely2ESRI(pth, 'r')
                reader.open()
                if reader.getGeometryType() != 'POLYGON':
                    raise IOError("Shapefile %s does not contain POLYGONS" %pth)
                
                shapefiles[id] = reader
        except:
            for reader in shapefiles.itervalues():
                reader.close()
            raise
        
        return shapefiles
    
    
    
    def _IndexNodeGeometries(self):
        '''
        Uses get_attribute_values() (Scenario function) to create proxy objects for Emme nodes.
        
        This is done to allow node locations to be loaded IN THE ORDER SPECIFIED BY THE FILE,
        regardless of whether those nodes are specified by a selector or by geometry. 
        '''
        indices, xtable, ytable = self.BaseScenario.get_attribute_values('NODE', ['x', 'y'])
        
        extents = min(xtable), min(ytable), max(xtable), max(ytable)
        
        spatialIndex = GridIndex(extents, marginSize= 1.0)
        proxies = {}
        
        for nodeNumber, index in indices.iteritems():
            x = xtable[index]
            y = ytable[index]
            
            #Using a proxy class defined in THIS file, because we don't yet
            #have the full network loaded.
            nodeProxy = NodeSpatialProxy(nodeNumber, x, y)
            spatialIndex.insertPoint(nodeProxy)
            proxies[nodeNumber] = nodeProxy
        
        return spatialIndex, proxies
    
    def _LoadZoneFromSelection(self, zoneElement, zoneAttributeId, tool, number, nodes):
        id = zoneElement.attrib['id']
        
        for selectionElement in zoneElement.findall('node_selector'):
            spec = {
                    "result": zoneAttributeId,
                    "expression": str(number),
                    "aggregation": None,
                    "selections": {
                        "node": selectionElement.text
                    },
                    "type": "NETWORK_CALCULATION"
                }
            
            try:
                tool(spec, scenario= self.BaseScenario)
            except ModuleError as me:
                raise IOError("Error loading zone '%s': %s" %(id, me))
        
        #Update the list of proxy nodes with the network's newly-loaded zones attribute
        indices, table = self.BaseScenario.get_attribute_values('NODE', [zoneAttributeId])
        for number, index in indices.iteritems():
            nodes[number].zone = table[index]
    
    def _LoadZoneFromGeometry(self, zoneElement, spatialIndex, shapefiles, number, nodes):
        id = zoneElement.attrib['id']
        
        for fromShapefileElement in zoneElement.findall('from_shapefile'):
            sid = fromShapefileElement.attrib['id']
            fid = int(fromShapefileElement.attrib['FID'])
            
            reader = shapefiles[sid]
            polygon = reader.readFrom(fid)
            
            nodesToCheck = spatialIndex.queryPolygon(polygon)
            for proxy in nodesToCheck:
                point = proxy.geometry
                
                if polygon.intersects(point):
                    proxy.zone = number
    
    def _GetAbsoluteFilepath(self, otherPath):
        '''
        For the shapefile path, this function checks if it is a relative path or not.
        If it is a relative path, it returns a valid absolute path based on the
        location of the XML Schema File.
        '''
        if path.isabs(otherPath):
            return otherPath
        
        return path.join(path.dirname(self.XMLBaseSchemaFile), otherPath)
    
    
    #---
    #---HYPER NETWORK GENERATION--------------------------------------------------------------------------
    
    def _PrepareNetwork(self, network, nodeProxies, lineGroupAttId):
        '''
        Prepares network attributes for transformation
        '''
        
        network.create_attribute('TRANSIT_LINE', 'group', 0)
        network.create_attribute('NODE', 'passing_groups', None) #Set of groups passing through but not stopping at the node
        network.create_attribute('NODE', 'stopping_groups', None) #Set of groups stopping at the node
        network.create_attribute('NODE', 'fare_zone', 0) #The number of the fare zone
        network.create_attribute('NODE', 'to_hyper_node', None) #Dictionary to get from the node to its hyper nodes
        network.create_attribute('LINK', 'role', 0) #Link topological role
        network.create_attribute('NODE', 'role', 0) #Node topological role
        
        #Initialize node attributes (incl. copying node zone)
        #Also, copy the zones loaded into the proxies
        for node in network.regular_nodes():
            node.passing_groups = set()
            node.stopping_groups = set()
            node.to_hyper_node = {}
            
            if node.number in nodeProxies:
                proxy = nodeProxies[node.number]
                node.fare_zone = proxy.zone
        
        #Determine stops & assign operators to nodes
        for line in network.transit_lines():
            group = int(line[lineGroupAttId])
            line.group = group
            
            for segment in line.segments(True):
                iNode = segment.i_node
                if segment.allow_boardings or segment.allow_alightings:
                    iNode.stopping_groups.add(group)
                    if group in iNode.passing_groups: iNode.passing_groups.remove(group)
                else:
                    if not group in iNode.stopping_groups: iNode.passing_groups.add(group)
        
        #Put this into a function to be able to break from deep loops using return
        def applyNodeRole(node):
            if not node.stopping_groups and not node.passing_groups:
                if node.is_centroid == False:
                    node.role = 1 #  Surface node without transit
                return #Skip nodes without an incident transit segment
            
            for link in node.outgoing_links():
                if link.i_node.is_centroid or link.j_node.is_centroid: continue
                for mode in link.modes:
                    if mode.type == 'AUTO':
                        node.role = 1 #Surface node
                        return
            for link in node.incoming_links():
                if link.i_node.is_centroid or link.j_node.is_centroid: continue
                for mode in link.modes:
                    if mode.type == 'AUTO':
                        node.role = 1 #Surface node
                        return
            node.role = 2 #Station node is a transit stop, but does NOT connect to any auto links

        #Determine node role. This needs to be done AFTER stops have been identified
        for node in network.regular_nodes(): applyNodeRole(node)
            
        #Determine link role. Needs to happen after node role's have been identified
        for link in network.links():
            i, j = link.i_node, link.j_node
            if i.is_centroid or j.is_centroid: continue #Link is a centroid connector    
            
            permitsWalk = False
            for mode in link.modes:
                if mode.type == 'AUX_TRANSIT': 
                    permitsWalk = True
                    break
            
            if i.role == 1 and j.role == 2 and permitsWalk: link.role = 1 #Station connector (access)
            elif i.role == 2 and j.role == 1 and permitsWalk: link.role = 1 #Station connector (egress)
            elif i.role == 2 and j.role == 2 and permitsWalk: link.role = 2 #Station transfer

    def _transform_network(self, network, number_of_groups, number_of_zones):
        
        total_nodes_0 = network.element_totals['regular_nodes']
        total_links_0 = network.element_totals['links']
        
        base_surface_nodes = []
        base_station_nodes = []
        for node in network.regular_nodes():
            if node.role == 1: base_surface_nodes.append(node)
            elif node.role == 2: base_station_nodes.append(node)
        
        transfer_grid = grid(number_of_groups + 1, number_of_groups + 1, set())
        zone_crossing_grid = grid(number_of_zones + 1, number_of_zones + 1, set())
        
        transfer_mode = network.mode(self.TransferModeId)
        
        line_ids = [line.id for line in network.transit_lines()]
        
        n_tasks = 2 * (len(base_surface_nodes) + len(base_station_nodes)) + len(line_ids)
        self._tracker.start_process(n_tasks)
        for i, node in enumerate(base_surface_nodes):
            self._transform_surface_node(node, transfer_grid, transfer_mode)
            self._tracker.complete_subtask()
        
        print ("Processed surface nodes")
        total_nodes_1 = network.element_totals['regular_nodes']
        total_links_1 = network.element_totals['links']
        _write("Created %s virtual road nodes." %(total_nodes_1 - total_nodes_0))
        _write("Created %s access links to virtual road nodes" %(total_links_1 - total_links_0))
        
        for i, node in enumerate(base_station_nodes):
            self._transform_station_node(node, transfer_grid, transfer_mode)
            self._tracker.complete_subtask()
        
        print ("Processed station nodes")
        total_nodes_2 = network.element_totals['regular_nodes']
        total_links_2 = network.element_totals['links']
        _write("Created %s virtual transit nodes." %(total_nodes_2 - total_nodes_1))
        _write("Created %s access links to virtual transit nodes" %(total_links_2 - total_links_1))
        
        for node in base_surface_nodes:
            self._connect_surface_or_station_node(node, transfer_grid)
            self._tracker.complete_subtask()
        for node in base_station_nodes:
            self._connect_surface_or_station_node(node, transfer_grid)
            self._tracker.complete_subtask()
        
        print ("Connected surface and station nodes")
        total_links_3 = network.element_totals['links']
        _write("Created %s road-to-transit connector links" %(total_links_3 - total_links_2))
        
        #TODO: ..................................................
        if self.SegmentINodeAttributeId is not None:
            def save_function(segment, i_node_id):
                segment[self.SegmentINodeAttributeId] = i_node_id
        else:
            def save_function(segment, i_node_id):
                pass
        
        for line_id in line_ids:
            self._process_transit_line(line_id, network, zone_crossing_grid, save_function)
            self._tracker.complete_subtask()
        
        print ("Processed transit lines")
        total_links_4 = network.element_totals['links']
        _write("Created %s in-line virtual links" %(total_links_4 - total_links_3))
        
        self._tracker.complete_task()
        
        return transfer_grid, zone_crossing_grid
    
    def _get_new_node_number(self, network, base_node_number):
        #TODO: ...........
        test_node = network.node(self._nextNodeId)
        while test_node is not None:
            self._nextNodeId += 1
            test_node = network.node(self._nextNodeId)
        return self._nextNodeId
    
    def _transform_surface_node(self, base_node, transfer_grid, transfer_mode):
        network = base_node.network
        
        '''
        NOTE TO SELF: When copying attributes to new nodes, REMEMBER that the
        the "special" attributes created in _PrepareNetwork(...) get copied
        as well! This includes pointers to objects - specifically Dictionaries -
        so UNDER NO CIRCUMSTANCES modify a copy's 'to_hyper_network' attribute
        since that modifies the base's dictionary as well.
        '''
        
        created_nodes = []
        links_created = 0
        
        #Create the virtual nodes for stops
        for group_number in base_node.stopping_groups:
            new_node = network.create_regular_node(self._get_new_node_number(network, base_node.number))
            
            #Copy the node attributes, including x, y coordinates
            for att in network.attributes('NODE'):
                new_node[att] = base_node[att]
            #newNode.label = "RS%s" %int(group_number)
            new_node.label = base_node.label
            
            
            #Attach the new node to the base node for later
            base_node.to_hyper_node[group_number] = new_node
            created_nodes.append((new_node, group_number))
            
            #Connect base node to operator node
            in_bound_link = network.create_link(base_node.number, new_node.number, [transfer_mode])
            out_bound_link = network.create_link(new_node.number, base_node.number, [transfer_mode])
            links_created += 2
            
            #Attach the transfer links to the grid for indexing
            transfer_grid[0, group_number].add(in_bound_link)
            transfer_grid[group_number, 0].add(out_bound_link)
        
        #Connect the virtual nodes to each other
        for tup_a, tup_b in get_combinations(created_nodes, 2): #Iterate through unique pairs of nodes
            node_a, group_a = tup_a
            node_b, group_b = tup_b
            link_ab = network.create_link(node_a.number, node_b.number, [transfer_mode])
            link_ba = network.create_link(node_b.number, node_a.number, [transfer_mode])
            links_created += 2
            
            transfer_grid[group_a, group_b].add(link_ab)
            transfer_grid[group_b, group_a].add(link_ba)
        
        #Create any virtual non-stop nodes
        for group_number in base_node.passing_groups:
            new_node = network.create_regular_node(self._get_new_node_number(network, base_node.number))
            
            #Copy the node attributes, including x, y coordinates
            for att in network.attributes('NODE'):
                new_node[att] = base_node[att]
            #newNode.label = "RP%s" %int(group_number)
            new_node.label = base_node.label
            
                
            #Attach the new node to the base node for later
            base_node.to_hyper_node[group_number] = new_node
            
            #Don't need to connect the new node to anything right now
        
    def _transform_station_node(self,  base_node, transfer_grid, transfer_mode):
        network = base_node.network
        
        virtual_nodes = []
        
        #Catalog and classify inbound and outbound links for copying
        outgoing_links = []
        incoming_links = []
        outgoing_connectors = []
        incoming_connectors = []
        for link in base_node.outgoing_links():
            if link.role == 1:
                outgoing_links.append(link)
            elif link.j_node.is_centroid: 
                if self.StationConnectorFlag:
                    outgoing_links.append(link)
                else:
                    outgoing_connectors.append(link)
        for link in base_node.incoming_links():
            if link.role == 1:
                incoming_links.append(link)
            elif link.i_node.is_centroid:
                if self.StationConnectorFlag:
                    incoming_links.append(link)
                else:
                    incoming_connectors.append(link)
        
        first = True
        for group_number in base_node.stopping_groups:
            if first:
                #Assign the existing node to the first group
                base_node.to_hyper_node[group_number] = base_node
                virtual_nodes.append((base_node, group_number))
                
                #Index the incoming and outgoing links to the Grid
                for link in incoming_links: transfer_grid[0, group_number].add(link)
                for link in outgoing_links: transfer_grid[group_number, 0].add(link)
                
                first = False
                #baseNode.label = "TS%s" %int(group_number)
                
            else:
                virtual_node = network.create_regular_node(self._get_new_node_number(network, base_node.number))
            
                #Copy the node attributes, including x, y coordinates
                for att in network.attributes('NODE'): virtual_node[att] = base_node[att]
                #virtualNode.label = "TS%s" %int(group_number)
                virtual_node.label = base_node.label
                
                #Assign the new node to its group number
                base_node.to_hyper_node[group_number] = virtual_node    
                virtual_nodes.append((virtual_node, group_number))
                
                #Copy the base node's existing centroid connectors to the new virtual node
                #TODO:..............................
                if not self.StationConnectorFlag:
                    for connector in outgoing_connectors:
                        new_link = network.create_link(virtual_node.number, connector.j_node.number, connector.modes)
                        for att in network.attributes('LINK'): new_link[att] = connector[att]
                    for connector in incoming_connectors:
                        new_link = network.create_link(connector.i_node.number, virtual_node.number, connector.modes)
                        for att in network.attributes('LINK'): new_link[att] = connector[att]
                    
                #Copy the base node's existing station connectors to the new virtual node
                for connector in outgoing_links:
                    new_link = network.create_link(virtual_node.number, connector.j_node.number, connector.modes)
                    for att in network.attributes('LINK'): new_link[att] = connector[att]
                    
                    transfer_grid[group_number, 0].add(new_link) #Index the new connector to the Grid
                    
                for connector in incoming_links:
                    new_link = network.create_link(connector.i_node.number, virtual_node.number, connector.modes)
                    for att in network.attributes('LINK'): new_link[att] = connector[att]
                    
                    transfer_grid[0, group_number].add(new_link) #Index the new connector to the Grid
                                 
        #Connect the virtual nodes to each other
        for tup_a, tup_b in get_combinations(virtual_nodes, 2): #Iterate through unique pairs of nodes
            node_a, group_a = tup_a
            node_b, group_b = tup_b

            link_ab = network.create_link(node_a.number, node_b.number, [transfer_mode])
            link_ba = network.create_link(node_b.number, node_a.number, [transfer_mode])

            transfer_grid[group_a, group_b].add( link_ab )
            transfer_grid[group_b, group_a].add( link_ba )
        
        for group in base_node.passing_groups:
            new_node = network.create_regular_node(self._get_new_node_number(network, base_node.number))
            
            for att in network.attributes('NODE'): new_node[att] = base_node[att]
            #newNode.label = "TP%s" %int(group)
            new_node.label = base_node.label
            
            base_node.to_hyper_node[group] = new_node
    
    def _connect_surface_or_station_node(self, base_node_1, transfer_grid):
        network = base_node_1.network
        
        #Theoretically, we should only need to look at outgoing links,
        #since one node's outgoing link is another node's incoming link.
        for link in base_node_1.outgoing_links():
            if link.role == 0: continue #Skip non-connector links
            
            base_node_2 = link.j_node
            
            for group_number_1 in base_node_1.stopping_groups:
                virtual_node_1 = base_node_1.to_hyper_node[group_number_1]
                
                for group_number_2 in base_node_2.stopping_groups:
                    virtual_node_2 = base_node_2.to_hyper_node[group_number_2]
                    
                    if network.link(virtual_node_1.number, virtual_node_2.number) is not None:
                        #Link already exists. Index it just in case
                        if group_number_1 != group_number_2:
                            transfer_grid[group_number_1, group_number_2].add(network.link(virtual_node_1.number, virtual_node_2.number))
                        continue 
                    
                    new_link = network.create_link(virtual_node_1.number, virtual_node_2.number, link.modes)
                    for att in network.attributes('LINK'): new_link[att] = link[att]
                    
                    #Only index if the group numbers are different. Otherwise, this is the only
                    #part of the code where intra-group transfers are identified, so DON'T do
                    #it to have the matrix be consistent.
                    if group_number_1 != group_number_2:
                        transfer_grid[group_number_1, group_number_2].add(new_link)
    
    def _process_transit_line(self, line_id, network, zone_transfer_grid, save_function):
        line = network.transit_line(line_id)
        group = line.group
        line_mode = set([line.mode])
        
        base_links = [segment.link for segment in line.segments(False)]
        new_itinerary = [base_links[0].i_node.to_hyper_node[group].number]
        for base_link in base_links:
            iv = base_link.i_node.to_hyper_node[group].number
            jv = base_link.j_node.to_hyper_node[group].number
            
            new_itinerary.append(jv)
            
            v_link = network.link(iv, jv)
            if v_link is None:
                v_link = network.create_link(iv, jv, line_mode)
                for att in network.attributes('LINK'): v_link[att] = base_link[att]
            else:
                v_link.modes |= line_mode
                
        new_line = network.create_transit_line('temp', line.vehicle.id, new_itinerary)
        for att in network.attributes('TRANSIT_LINE'): new_line[att] = line[att]
        
        for segment in line.segments(True):
            new_segment = new_line.segment(segment.number)
            for att in network.attributes('TRANSIT_SEGMENT'): new_segment[att] = segment[att]
            
            save_function(new_segment, segment.i_node.number)
            
            link = segment.link
            if link is not None:
                fzi = link.i_node.fare_zone
                fzj = link.j_node.fare_zone
                
                if fzi != fzj and fzi != 0 and fzj != 0:
                    #Add the segment's identifier, since changeTransitLineId de-references
                    #the line copy.
                    zone_transfer_grid[fzi, fzj].add((line_id, segment.number))
        
        network.delete_transit_line(line_id)
        #TODO:..........
        _editing.changeTransitLineId(new_line, line_id)
    
    def _index_station_connectors(self, network, transfer_grid, station_groups, group_ids_2_int):
        print ("Indexing station connectors")        
        for line_group_id, station_centroids in station_groups.items():
            idx = group_ids_2_int[line_group_id]
            for node_id in station_centroids:
                centroid = network.node(node_id)
                #Skip non-zones
                if not centroid.is_centroid: 
                    continue 
                
                for link in centroid.outgoing_links():
                    if idx in link.j_node.stopping_groups:
                        transfer_grid[0, idx].add(link)
                for link in centroid.incoming_links():
                    if idx in link.i_node.stopping_groups:
                        transfer_grid[idx, 0].add(link)
            print ("Indexed connectors for group %s" %line_group_id)
                
    
    #---              
    #---LOAD FARE RULES-----------------------------------------------------------------------------------
    
    def _apply_fare_rules(self, network, fare_rules_element,
                        group_transfer_grid, zone_crossing_grid,
                        group_ids_2_int, zone_ids_2_int, segment_fare_attribute, link_fare_attribute):
        
        lines_id_exed_by_group = {}
        for line in network.transit_lines():
            group = line.group
            
            if group in lines_id_exed_by_group:
                lines_id_exed_by_group[group].append(line)
            else:
                lines_id_exed_by_group[group] = [line]
        
        for fare_element in fare_rules_element.findall('fare'):
            typ = fare_element.attrib['type']
            
            if typ == 'initial_boarding':
                self._apply_initial_boarding_fare(fare_element, group_ids_2_int, zone_ids_2_int, group_transfer_grid, link_fare_attribute)
            elif typ == 'transfer':
                self._apply_transfer_boarding_fare(fare_element, group_ids_2_int, group_transfer_grid, link_fare_attribute)
            elif typ == 'distance_in_vehicle':
                self._apply_fare_by_distance(fare_element, group_ids_2_int, lines_id_exed_by_group, segment_fare_attribute)
            elif typ == 'zone_crossing':
                self._apply_zone_crossing_fare(fare_element, group_ids_2_int, zone_ids_2_int, zone_crossing_grid, network, segment_fare_attribute)
            
            self._tracker.complete_subtask()
            
            
    def _apply_initial_boarding_fare(self, fare_element, group_ids_2_int, zone_ids_2_int, transfer_grid, link_fare_attribute):
        cost = float(fare_element.attrib['cost'])
        
        with _trace("Initial Boarding Fare of %s" %cost):
            group_id = fare_element.find('group').text
            _write("Group: %s" %group_id)
            
            group_number = group_ids_2_int[group_id]
            
            in_zone_element = fare_element.find('in_zone')
            if in_zone_element is not None:
                zone_id = in_zone_element.text
                zone_number = zone_ids_2_int[zone_id]
                _write("In zone: %s" %zone_id)
                
                check_link = lambda link: link.i_node.fare_zone == zone_number
            else:
                check_link = lambda link: True
            
            include_all_element = fare_element.find('include_all_groups')
            if include_all_element is not None:
                include_all = self.__BOOL_PARSER[include_all_element.text]
                _write("Include all groups: %s" %include_all)
            else:
                include_all = True
            count = 0
            if include_all:
                for x_index in xrange(transfer_grid.x):
                    for link in transfer_grid[x_index, group_number]:
                        if check_link(link): 
                            link[link_fare_attribute] += cost
                            count += 1
            else:
                for link in transfer_grid[0, group_number]:
                    if check_link(link):
                        link[link_fare_attribute] += cost
                        count += 1   
            _write("Applied to %s links." %count)
    
    def _apply_transfer_boarding_fare(self, fare_element, group_ids_2_int, transfer_grid, link_fare_attribute):
        cost = float(fare_element.attrib['cost'])
        
        with _trace("Transfer Boarding Fare of %s" %cost):
            from_group_id = fare_element.find('from_group').text
            from_number = group_ids_2_int[from_group_id]
            _write("From Group: %s" %from_group_id)
            
            to_group_id = fare_element.find('to_group').text
            to_number = group_ids_2_int[to_group_id]
            _write("To Group: %s" %to_group_id)
            
            bi_directional_element = fare_element.find('bidirectional')
            if bi_directional_element is not None:
                bi_directional = self.__BOOL_PARSER[bi_directional_element.text.upper()]
                _write("Bidirectional: %s" %bi_directional)
            else:
                bi_directional = False
            
            count = 0
            for link in transfer_grid[from_number, to_number]:
                link[link_fare_attribute] += cost
                count += 1
            
            if bi_directional:
                for link in transfer_grid[to_number, from_number]:
                    link[link_fare_attribute] += cost
                    count += 1
            _write("Applied to %s links." %count)
    
    def _apply_fare_by_distance(self, fare_element, group_ids_2_int, lines_id_exed_by_group, segment_fare_attribute):
        cost = float(fare_element.attrib['cost'])
        with _trace("Fare by Distance of %s" %cost):
            group_id = fare_element.find('group').text
            group_number = group_ids_2_int[group_id]
            _write("Group: %s" %group_id)
            count = 0
            for line in lines_id_exed_by_group[group_number]:
                for segment in line.segments(False):
                    segment[segment_fare_attribute] += segment.link.length * cost
                    count += 1
            _write("Applied to %s segments." %count)
    
    def _apply_zone_crossing_fare(self, fare_element, group_ids_2_int, zone_ids_2_int, crossing_grid, network, segment_fare_attribute):
        cost = float(fare_element.attrib['cost'])
        with _trace("Zone Crossing Fare of %s" %cost):
            group_id = fare_element.find('group').text
            group_number = group_ids_2_int[group_id]
            _write("Group: %s" %group_id)
            from_zone_id = fare_element.find('from_zone').text
            from_number = zone_ids_2_int[from_zone_id]
            _write("From Zone: %s" %from_zone_id)
            to_zone_id = fare_element.find('to_zone').text
            to_number = zone_ids_2_int[to_zone_id]
            _write("To Zone: %s" %to_zone_id)
            bi_directional_element = fare_element.find('bidirectional')
            if bi_directional_element is not None:
                bi_directional = self.__BOOL_PARSER[bi_directional_element.text.upper()]
                _write("Bidirectional: %s" %bi_directional)
            else:
                bi_directional = False
            count = 0
            for line_id, segment_number in crossing_grid[from_number, to_number]:
                line = network.transit_line(line_id)
                if line.group != group_number: continue
                line.segment(segment_number)[segment_fare_attribute] += cost
                count += 1
            if bi_directional:
                for line_id, segment_number in crossing_grid[to_number, from_number]:
                    line = network.transit_line(line_id)
                    if line.group != group_number: continue
                    line.segment(segment_number)[segment_fare_attribute] += cost
                    count += 1
            _write("Applied to %s segments." %count)
        
    def _Check_for_negative_fares(self, network, segment_fare_attribute, link_fare_attribute):
        negative_links = []
        negative_segments = []
        for link in network.links():
            cost = link[link_fare_attribute]
            if cost < 0.0: negative_links.append(link)
        for segment in network.transit_segments():
            cost = segment[segment_fare_attribute]
            if cost < 0.0: negative_segments.append(segment)
        if (len(negative_links) + len(negative_segments)) > 0:
            print ("WARNING: Found %s links and %s segments with negative fares" %(len(negative_links), len(negative_segments)))
            pb = _m.PageBuilder(title="Negative Fares Report")
            h = HTML()
            h.h2("Links with negative fares")
            t = h.table()
            r = t.tr()
            r.th("link")
            r.th("cost")
            for link in negative_links:
                r = t.tr()
                r.td(str(link))
                r.td(str(link[link_fare_attribute]))
            
            h.h2("Segments with negative fares")
            t = h.table()
            r = t.tr()
            r.th("segment")
            r.th("cost")
            for segment in negative_segments:
                r = t.tr()
                r.td(segment.id)
                r.td(segment[segment_fare_attribute])
            
            pb.wrap_html(body=str(h))
            
            _write("LINKS AND SEGMENTS WITH NEGATIVE FARES", value=pb.render())

    #---              
    #---MODELLER INTERFACE FUNCTIONS----------------------------------------------------------------------      
    
    @_m.method(return_type=str)
    def preload_auxtr_modes(self):
        options = []
        h = HTML()
        for id, type, description in _util.getScenarioModes(self.BaseScenario,  ['AUX_TRANSIT']):
            text = "%s - %s" %(id, description)
            options.append(str(h.option(text, value= id)))
        return "\n".join(options)
    
    @_m.method(return_type=str)
    def preload_scenario_link_attributes(self):
        options = []
        h = HTML()
        for exatt in self.BaseScenario.extra_attributes():
            if exatt.type != 'LINK': continue
            text = "%s - %s" %(exatt.name, exatt.description)
            options.append(str(h.option(text, value= exatt.name)))
        return "\n".join(options)

    @_m.method(return_type=str)
    def preload_scenario_segment_attributes(self):
        options = []
        h = HTML()
        for exatt in self.BaseScenario.extra_attributes():
            if exatt.type != 'TRANSIT_SEGMENT': continue
            text = "%s - %s" %(exatt.name, exatt.description)
            options.append(str(h.option(text, value= exatt.name)))
        return "\n".join(options)
    
    @_m.method(return_type=_m.TupleType)
    def percent_completed(self):
        return self._tracker.getProgress()
                
    @_m.method(return_type=str)
    def tool_run_msg_status(self):
        return self.tool_run_msg
        