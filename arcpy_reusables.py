"""
Script Name:     arcpy_reusables.py
Description:     A set of custom, reusable ArcPy functions for streamlined geospatial analysis across multiple projects.

Author:          Meg Walker
Created:         02-03-2024
Last Modified:   06-09-2024

ArcGIS Version: ArcGIS Pro 3.2.0
ArcPy Version:  3.2
Python Version: Python 3.10.0
Dependencies:   arcpy, datetime, os, pandas

Notes:
    To be used in VSCode and called from ArcGIS Pro notebook.

"""

import arcpy
import pandas as pd
import os
from datetime import datetime as dt

def setArcGISEnv(**environment_settings):
    """Sets the ArcGIS workspace and environment settings.

    Parameters:
        # workspace_path (str): The path to the ArcGIS workspace.
        **environment_settings: A dictionary of ArcGIS environment settings to set.

    Returns:
        None.
    """
    # Set the environment settings
    for environment_setting, environment_value in environment_settings.items():
        setattr(arcpy.env, environment_setting, environment_value)  

def resetArcGISEnv():
    """Resets all ArcGIS environment settings to their default values."""
    arcpy.ResetEnvironments()

def arcgisTableToDF(input_feature_class, input_fields=None, where_clause=None, drop_boolean=True):
    """Converts an ArcGIS table into a pandas DF with an object ID index, and any selected
    input fields using an arcpy.da.SearchCursor. If input_fields is empty, all fields are selected.
    
    Parameters:
        input_feature_class (str):  An input feature classes to export.
        input_fields (list of str, optional): A list of fields to keep.
        input_fields (str, optional): Conditions for selecting features to export.
        
    Returns:
        df: pd.DataFrame
    """
    # Assign FieldName.
    OIDFieldName = arcpy.Describe(input_feature_class).OIDFieldName
    
    # If there are a subset of fields to use, create a list with fields to keep.
    if input_fields:
        final_fields = [OIDFieldName] + input_fields
        # Else, create a list with all field names.
    else:
        final_fields = [field.name for field in arcpy.ListFields(input_feature_class)]
    
    # Export row by row.
    data = [row for row in arcpy.da.SearchCursor(input_feature_class, final_fields, where_clause=where_clause)]
    
    # Subset DF.
    df = pd.DataFrame(data, columns=final_fields)
    
    # Assign index for new DF.
    df = df.set_index(OIDFieldName, drop=drop_boolean)
    
    return df

def convert_to_singlepart(input_feature_class, output_gdb):
    """
    Takes an input feature class, extracts only the necessary columns and converts them to single-part features.

    Parameters:
        input_feature_class (str): The input feature class name.
        output_gdb (str): The path to the output geodatabase.

    Returns:
        None.
        
    Note:
        The conversion to single-part features does not impact linestrings.

    """
    # Convert each of the features to singlepart. Note: this won't impact linestrings
    temp_fc_name = input_feature_class + "_tempSinglePart"
    new_feature_class = output_gdb + "\\" + temp_fc_name

    delete_feature_class_if_exists(new_feature_class)
    
    try:
        # Convert to single part
        arcpy.management.MultipartToSinglepart(input_feature_class, new_feature_class)
        delete_and_replace_feature_class(input_feature_class, new_feature_class)
        
    except Exception as e:
        print(f"Error converting {input_feature_class} to single part: {str(e)}")

def copy_feature_classes_to_gdb(input_feature_classes, output_gdb, new_names):
    """Copies input feature classes to the same geodatabase with new names based on the provided list.

    Parameters:
        input_feature_classes (list of str): A list of input feature class names.
        output_gdb (str): The path to the output geodatabase.
        new_names (list of str): A list of new names for the copied feature classes.

    Returns:
        copied_feature_classes (list of str): A list of the names of the newly copied feature classes.
    """
    if len(input_feature_classes) != len(new_names):
        raise ValueError("The number of input feature classes must match the number of new names.")

    copied_feature_classes = []

    for input_feature_class, new_name in zip(input_feature_classes, new_names): 
        # Construct the full path to the new feature class within the output geodatabase
        new_feature_class = output_gdb + "\\" + new_name
            
        delete_feature_class_if_exists(new_feature_class)

        try:
            # Copy the input feature class to the output geodatabase with the new name
            arcpy.CopyFeatures_management(input_feature_class, new_feature_class)
            copied_feature_classes.append(new_name)
        except Exception as e:
            print(f"Error copying {input_feature_class} to {new_name}: {str(e)}")

    return copied_feature_classes

def delete_and_replace_feature_class(old_feature_class, new_feature_class):
    """
    Replaces a feature class with an updated version and deletes temporary files.

    Parameters:
        old_feature_class (list of str): The current feature class to be updated.
        new_feature_class (str): The updated feature class used to replace the previous version.

    Returns:
        None.
    """
    # Remove the previous feature class.
    delete_feature_class_if_exists(old_feature_class)
    # Copy the updated feature class to new location.
    arcpy.CopyFeatures_management(new_feature_class, old_feature_class)
    # Remove the temporary feature class used.
    arcpy.Delete_management(new_feature_class)

def delete_feature_class_if_exists(input_feature_class):
    """
    Deletes a feature class if it exists in the geodatabase, helping to avoid errors when rerunning the script.

    Parameters:
        input_feature_class (str): The input feature class to be deleted.

    Returns:
        None.
    """
    
    if arcpy.Exists(input_feature_class):
        # If the feature class already exists, delete it
        arcpy.Delete_management(input_feature_class)

def get_field_names(input_feature_class):
    """
    Gets a list of field names in a feature class.
    
    Parameters:
        input_feature_class (str): The feature class to get the column names for.

    Returns:
        fields (list of str): The list of field names.
    """
    fields = [field.name for field in arcpy.ListFields(input_feature_class)]
    
    return fields

def select_columns_from_list(input_feature_class, output_gdb, column_list):
    """
    Copies input feature class to the same geodatabase with a new name based on the provided list of columns.

    Parameters:
        input_feature_class (str): The name of the input feature class.
        output_gdb (str): The path to the output geodatabase.
        column_list (list of str): A list of column names to keep.

    Returns:
        None.
    """
    # new_feature_class = output_gdb + "\\" + feature_class + "_temp"
    new_feature_class = input_feature_class + "_temp"
    
    try:
        # Ensure any previous temporary feature class is deleted.
        delete_feature_class_if_exists(new_feature_class)

        # Create a field mapping object.
        field_mappings = arcpy.FieldMappings()

        # Get the fields from the input feature class.
        fields = column_list

        # Loop through the fields and add the desired fields to the field mapping
        for field in fields:
            # Check if the column_name exists in the list of fields
            if field in get_field_names(input_feature_class):
                field_map = arcpy.FieldMap()
                field_map.addInputField(input_feature_class, field)
                field_mappings.addFieldMap(field_map)
            else:
                print("Column '" + field + "' not present in the layer '" + input_feature_class + "'.")

        # Create the new feature class with the subset of columns.
        arcpy.FeatureClassToFeatureClass_conversion(input_feature_class, output_gdb, new_feature_class, field_mapping=field_mappings)
        # Replace the original feature class with the new one.
        delete_and_replace_feature_class(input_feature_class, new_feature_class)

    except Exception as e:
        print(f"Error subsetting {new_feature_class}: {str(e)}")

def subsetFeatures(input_feature_classes, output_gdb, list_of_column_lists):
    """Subsets features using a for loop and other predefined functions. 
        The nested list should be in the same order as the list of feature classes.
    
        Parameters:
            input_feature_classes (list of str): A list of input feature classes to clean.
            output_gdb (str): The path to the output geodatabase.
            column_list (list of str): A nested list of column names to keep for each feature class.
        
        Returns:
            None.
    """
    for feature_class, list_index in zip(input_feature_classes, list(range(0,len(input_feature_classes),1))):
        # Dimensionality reduction.
        select_columns_from_list(feature_class, output_gdb, list_of_column_lists[list_index])
        # Convert to singlepart where required
        #convert_to_singlepart(feature_class, output_gdb)
        

def rename_fields(input_feature_class, output_gdb, field_name_mapping):
    """
    Rename fields in a feature class.

    Parameters:
    - input_feature_class (str): Path to the input feature class.
    - output_gdb (str): Path to the output geodatabase.
    - field_name_mapping (dict): Dictionary mapping old field names to new field names.

    Example:
    field_mapping = {"OldField1": "NewField1", "OldField2": "NewField2"}
    rename_fields("C:/path/to/your.gdb/your_feature_class", "C:/path/to/your_output.gdb", field_mapping)
    """
    # Check if the input feature class exists
    if not arcpy.Exists(input_feature_class):
        print(f"Error: Feature class '{input_feature_class}' not found.")
        return

    # Create a name for the output feature class
    output_feature_class = os.path.join(output_gdb, os.path.basename(input_feature_class) + "_renamed")

    # Copy the input feature class to the output geodatabase
    arcpy.management.CopyFeatures(input_feature_class, output_feature_class)

    # Loop through the field name mapping dictionary
    for old_field, new_field in field_name_mapping.items():
        try:
            # Use AlterField_management to rename the fields in the output feature class
            arcpy.management.AlterField(output_feature_class, old_field, new_field)
            print(f"Field '{old_field}' renamed to '{new_field}'.")
        except arcpy.ExecuteError:
            print(f"Error renaming field '{old_field}' to '{new_field}'.")
            print(arcpy.GetMessages())

'''
def rename_fields(input_feature_class, output_gdb, field_name_mapping):
    """
    Rename fields in a feature class.

    Parameters:
    - feature_class (str): Path to the input feature class.
    - field_name_mapping (dict): Dictionary mapping old field names to new field names.

    Example:
    field_mapping = {"OldField1": "NewField1", "OldField2": "NewField2"}
    rename_fields("C:/path/to/your.gdb/your_feature_class", field_mapping)
    """
    # Check if the feature class exists
    if not arcpy.Exists(input_feature_class):
        print(f"Error: Feature class '{input_feature_class}' not found.")
        return

    # Loop through the field name mapping dictionary
    for old_field, new_field in field_name_mapping.items():
        try:
            # Use AlterField_management to rename the fields
            arcpy.management.AlterField(input_feature_class, old_field, new_field)
            print(f"Field '{old_field}' renamed to '{new_field}'.")
        except arcpy.ExecuteError:
            print(f"Error renaming field '{old_field}' to '{new_field}'.")
            print(arcpy.GetMessages())

'''
def deleteFieldInFeatureClassIfExists(input_feature_class, field_name):
    # Check if the field exists
    field_list = [field.name for field in arcpy.ListFields(input_feature_class)]
    
    if field_name in field_list:
        # If the field exists, delete it
        arcpy.DeleteField_management(input_feature_class, field_name)
        print(f"Field '{field_name}' deleted from {input_feature_class}.")
    else:
        print(f"Field '{field_name}' does not exist in {input_feature_class}.")


def debug_JoinTable(input_feature_class, output_gdb, join_table, join_col1, join_col2, fieldToAdd, fieldType):
    inFeatures = output_gdb + "/" + input_feature_class
    layerName = "layer_temp"
    out_feature_class = "join_table_temp"
    outFeature = output_gdb + "/" + out_feature_class
    #fieldType = arcpy.ListFields(join_table,fieldToAdd)[0]
    
    expression = "!"+ join_table + "." + fieldToAdd + "!"
    
    delete_feature_class_if_exists(out_feature_class)
    deleteFieldInFeatureClassIfExists(input_feature_class, fieldToAdd)
    
    if arcpy.Exists(layerName):
        arcpy.Delete_management(layerName)
    # Add the new field
    arcpy.management.AddField(inFeatures, fieldToAdd, fieldType)
        
    # Create a feature layer
    arcpy.management.MakeFeatureLayer(inFeatures,  layerName)
        
    # Join the feature layer to a table
    arcpy.management.AddJoin(layerName, join_col1, join_table, join_col2)
        
    # Populate the newly created field with values from the joined table
    arcpy.management.CalculateField(layerName, fieldToAdd, expression, "PYTHON")
        
    # Remove the join
    arcpy.management.RemoveJoin(layerName, join_table)
        
    # Copy the layer to a new permanent feature class
    arcpy.management.CopyFeatures(layerName, outFeature)
    
    delete_feature_class_if_exists(input_feature_class)
    copy_feature_classes_to_gdb([outFeature], output_gdb, [input_feature_class])

