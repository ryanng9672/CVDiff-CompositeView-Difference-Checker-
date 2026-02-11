import os
import pandas as pd
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import argparse
import sys
import re

def get_picture_name_from_xml(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        header = root.find('Header')
        if header is not None:
            name_element = header.find('Name')
            if name_element is not None and name_element.text:
                name = name_element.text.strip()
                if 'TEMP_' not in name and '*' not in name:
                    return name
                else:
                    return None
        return None
    except Exception as e:
        print(f"ERROR reading {xml_file}: {e}")
        return None

def normalize_xml_element(element, ignore_tags={'Id', 'Link'}):
    if element.tag in ignore_tags:
        return None
    new_elem = ET.Element(element.tag, element.attrib)
    new_elem.text = element.text
    new_elem.tail = element.tail
    for child in element:
        normalized_child = normalize_xml_element(child, ignore_tags)
        if normalized_child is not None:
            new_elem.append(normalized_child)
    return new_elem

def remove_guid_from_value_tags(root):
    guid_pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)
    for value_elem in root.iter('Value'):
        if value_elem.text:
            if guid_pattern.fullmatch(value_elem.text.strip()):
                value_elem.text = 'GUID_PLACEHOLDER'
    return root

def xml_to_comparable_string(xml_file, ignore_tags={'Id', 'Link'}):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        root = remove_guid_from_value_tags(root)
        normalized_root = normalize_xml_element(root, ignore_tags)
        xml_string = ET.tostring(normalized_root, encoding='unicode', method='xml')
        xml_string = re.sub(r'\s+', ' ', xml_string).strip()
        return xml_string
    except Exception as e:
        print(f"ERROR parsing {xml_file}: {e}")
        return None

def compare_xml_files(old_xml, new_xml):
    old_str = xml_to_comparable_string(old_xml)
    new_str = xml_to_comparable_string(new_xml)
    if old_str is None or new_str is None:
        return 'DIFFERENT'  
    if old_str == new_str:
        return 'SAME'
    else:
        return 'DIFFERENT'

def find_latest_diffreport_csv(diffreport_folder, report_type):
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    if report_type == "Composite":
        base_filename = "CompositeView_Diff"
    else:
        base_filename = "Substation_Diff"
    latest_csv = None
    latest_date = None
    for day in weekdays:
        csv_filename = f"{base_filename}_{day}.csv"
        csv_path = os.path.join(diffreport_folder, csv_filename)
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                df.columns = df.columns.str.strip()
                if 'Last_Update_Date' in df.columns:
                    max_date_str = df['Last_Update_Date'].dropna().max()
                    if pd.notna(max_date_str):
                        try:
                            if '/' in str(max_date_str):
                                max_date = datetime.strptime(str(max_date_str), '%d/%m/%Y')
                            else:
                                max_date = datetime.strptime(str(max_date_str), '%Y-%m-%d')
                            if latest_date is None or max_date > latest_date:
                                latest_date = max_date
                                latest_csv = csv_path
                        except:
                            continue
            except Exception as e:
                print(f"ERROR reading {csv_path}: {e}")
                continue
    return latest_csv

def find_backup_folder(date_str, report_type, backup_base_path):
    if report_type == "Composite":
        subfolder = "Composite"
    elif report_type == "Substation":
        subfolder = "Substation"
    else:
        return None
    folder_path = os.path.join(backup_base_path, date_str, subfolder)
    if os.path.exists(folder_path):
        return folder_path
    return None

def get_all_date_folders(backup_base_path):
    date_folders = []
    date_pattern = re.compile(r'^\d{8}$')
    if not os.path.exists(backup_base_path):
        return []
    for item in os.listdir(backup_base_path):
        item_path = os.path.join(backup_base_path, item)
        if os.path.isdir(item_path) and date_pattern.match(item):
            try:
                datetime.strptime(item, '%Y%m%d')
                date_folders.append(item)
            except:
                continue
    date_folders.sort()
    return date_folders

def get_all_xml_files_from_folder(folder_path):
    if not folder_path or not os.path.exists(folder_path):
        return {}
    xml_dict = {}
    for filename in os.listdir(folder_path):
        if filename.endswith('.xml'):
            xml_path = os.path.join(folder_path, filename)
            pic_name = get_picture_name_from_xml(xml_path)
            if pic_name:
                xml_dict[pic_name] = xml_path
    return xml_dict

def compare_and_update(report_type, backup_base_path, diffreport_folder):
    print(f"\n========== {report_type} COMPARISON ==========")
    os.makedirs(diffreport_folder, exist_ok=True)
    today = datetime.now()
    today_weekday = today.strftime('%a')
    date_folders = get_all_date_folders(backup_base_path)
    if len(date_folders) == 0:
        print(f"ERROR: No valid date folders found in {backup_base_path}")
        return
    print(f"\nFound {len(date_folders)} date folders:")
    for df in date_folders:
        print(f"  - {df}")
    if len(date_folders) < 2:
        print(f"\nWARNING: Need at least 2 date folders to compare, found only {len(date_folders)}")
        return
    old_date_str = date_folders[-2]
    new_date_str = date_folders[-1]
    print(f"\n✓ Auto-selected comparison (latest 2 folders):")
    print(f"  OLD version: {old_date_str}")
    print(f"  NEW version: {new_date_str}")
    old_date_display = datetime.strptime(old_date_str, '%Y%m%d').strftime('%Y-%m-%d')
    new_date_display = datetime.strptime(new_date_str, '%Y%m%d').strftime('%Y-%m-%d')
    old_report_file = find_latest_diffreport_csv(diffreport_folder, report_type)
    if old_report_file:
        print(f"\nLOADING old report: {old_report_file}")
        df_master = pd.read_csv(old_report_file)
        df_master.columns = df_master.columns.str.strip()
        if 'PIC_Name' in df_master.columns:
            df_master.rename(columns={'PIC_Name': 'Picture Name'}, inplace=True)
        if 'Last_Update_Date' in df_master.columns:
            def convert_date(date_str):
                if pd.isna(date_str):
                    return None
                try:
                    dt = datetime.strptime(str(date_str), '%d/%m/%Y')
                    return dt.strftime('%Y-%m-%d')
                except:
                    try:
                        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
                        return dt.strftime('%Y-%m-%d')
                    except:
                        return None
            df_master['Last_Update_Date'] = df_master['Last_Update_Date'].apply(convert_date)
    else:
        print(f"\nNO old report found, creating NEW report")
        df_master = pd.DataFrame(columns=['Picture Name', 'Last_Update_Date', 'Diff_Result'])
    backup_folder_old = find_backup_folder(old_date_str, report_type, backup_base_path)
    backup_folder_new = find_backup_folder(new_date_str, report_type, backup_base_path)
    if not backup_folder_old:
        print(f"ERROR: Cannot find backup folder for {old_date_str}")
        return
    if not backup_folder_new:
        print(f"ERROR: Cannot find backup folder for {new_date_str}")
        return
    print(f"OLD version folder: {backup_folder_old}")
    print(f"NEW version folder: {backup_folder_new}")
    old_xml_dict = get_all_xml_files_from_folder(backup_folder_old)
    new_xml_dict = get_all_xml_files_from_folder(backup_folder_new)
    print(f"OLD version has {len(old_xml_dict)} valid XML files")
    print(f"NEW version has {len(new_xml_dict)} valid XML files")
    new_data = []
    unchanged_count = 0
    id_only_count = 0
    updated_count = 0
    new_count = 0
    print(f"\nCOMPARING {len(new_xml_dict)} files using XML parsing...")
    for idx, (pic_name, new_xml) in enumerate(new_xml_dict.items()):
        if (idx + 1) % 100 == 0:
            print(f"  PROCESSED {idx + 1}/{len(new_xml_dict)}...")
        if pic_name in old_xml_dict:
            old_xml = old_xml_dict[pic_name]
            comparison_result = compare_xml_files(old_xml, new_xml)
            if comparison_result == 'SAME':
                id_only_count += 1
                old_date = df_master[df_master['Picture Name'] == pic_name]['Last_Update_Date'].values
                last_date = old_date[0] if len(old_date) > 0 else old_date_display
                new_data.append({
                    'Picture Name': pic_name,
                    'Last_Update_Date': last_date,
                    'Diff_Result': 'NIL'
                })
            else:
                updated_count += 1
                new_data.append({
                    'Picture Name': pic_name,
                    'Last_Update_Date': new_date_display,
                    'Diff_Result': 'UPDATED'
                })
        else:
            new_count += 1
            new_data.append({
                'Picture Name': pic_name,
                'Last_Update_Date': new_date_display,
                'Diff_Result': 'NEW'
            })
    deleted_count = 0
    for pic_name in old_xml_dict.keys():
        if pic_name not in new_xml_dict:
            deleted_count += 1
            old_date = df_master[df_master['Picture Name'] == pic_name]['Last_Update_Date'].values
            last_date = old_date[0] if len(old_date) > 0 else old_date_display
            new_data.append({
                'Picture Name': pic_name,
                'Last_Update_Date': last_date,
                'Diff_Result': 'DELETED'
            })
    df_new = pd.DataFrame(new_data)
    df_new = df_new.sort_values(by='Picture Name', ascending=True)
    print(f"\n========== STATISTICS ==========")
    print(f"Comparing: {old_date_str} vs {new_date_str}")
    print(f"TOTAL files: {len(df_new)}")
    print(f"NEW: {new_count}")
    print(f"DELETED: {deleted_count}")
    print(f"UPDATED: {updated_count}")
    print(f"NIL (ID/GUID only): {id_only_count}")
    if report_type == "Composite":
        csv_filename = f"CompositeView_Diff_{today_weekday}.csv"
    else:
        csv_filename = f"Substation_Diff_{today_weekday}.csv"
    new_csv_file = os.path.join(diffreport_folder, csv_filename)
    print(f"\nSAVING updated report to: {new_csv_file}")
    df_new.to_csv(new_csv_file, index=False, encoding='utf-8-sig')
    print(f"COMPLETED {report_type} report update!\n")
def interactive_path_input():
    print("\n" + "="*80)
    print("XML BACKUP COMPARISON - INTERACTIVE MODE")
    print("="*80)
    print("\nPlease choose how to configure paths:")
    print("-" * 80)
    print("1. Type 'Draft' or 'draft'  → Use default paths (admssim01)")
    print("2. Type '-'                 → Show command-line usage guide")
    print("3. Enter custom path        → Manually specify backup folder path")
    print("4. Press ENTER only         → Use default paths")
    print("-" * 80)
    user_input = input("\nYour choice: ").strip()
    if user_input.lower() == 'draft' or user_input == '':
        print("\n✓ Using default paths:")
        backup_path = r"\\admssim01\ADMS_DataEngineering\CompositeViewBackup"#path
        output_path = None
        report_type = 'both'
        print(f"  Backup path: {backup_path}")
        print(f"  Output path: {backup_path}\\DiffReport (default)")
        print(f"  Report type: {report_type.upper()}")
        return backup_path, output_path, report_type
    elif user_input == '-':
        print("\n" + "="*80)
        print("COMMAND-LINE USAGE GUIDE")
        print("="*80)
        print("\nTo run this program with custom paths from command line:")
        print("-" * 80)
        print("\nBasic usage:")
        print('  CVBackupCompare.exe --backup-path "YOUR_PATH"\n')
        print("Available parameters:")
        print("  --backup-path PATH")
        print("      Base path to XML backup folders")
        print('      Example: --backup-path "C:\\test"')
        print()
        print("  --output PATH")
        print("      Output folder for DiffReport CSV files")
        print('      Default: <backup-path>/DiffReport')
        print('      Example: --output "C:\\Reports\\DiffReport"')
        print()
        print("  --report-type TYPE")
        print("      Type of report to generate: composite, substation, or both")
        print('      Default: both')
        print('      Example: --report-type composite')
        print("="*80)
        input("\nPress ENTER to exit...")
        return None
    else:
        print("\n" + "="*80)
        print("CUSTOM PATH CONFIGURATION")
        print("="*80)
        backup_path = user_input
        print(f"\nBackup path set to: {backup_path}")
        output_input = input("\nEnter output folder path (or press ENTER for default): ").strip()
        if output_input == '':
            output_path = None
            print(f"Using default: {backup_path}\\DiffReport")
        else:
            output_path = output_input
        print("\nReport type options:")
        print("  1. composite  - Only CompositeView")
        print("  2. substation - Only Substation")
        print("  3. both       - Both reports (default)")
        report_input = input("\nEnter report type (or press ENTER for 'both'): ").strip().lower()
        if report_input in ['composite', 'substation', 'both']:
            report_type = report_input
        elif report_input == '':
            report_type = 'both'
        else:
            print(f"Invalid report type '{report_input}', using 'both'")
            report_type = 'both'
        print("\n" + "-"*80)
        print("Configuration summary:")
        print(f"  Backup path: {backup_path}")
        if output_path:
            print(f"  Output path: {output_path}")
        else:
            print(f"  Output path: {backup_path}\\DiffReport (default)")
        print(f"  Report type: {report_type.upper()}")
        print("-"*80)
        confirm = input("\nProceed with these settings? (Y/n): ").strip().lower()
        if confirm == 'n':
            print("\n✗ Configuration cancelled.")
            input("Press ENTER to exit...")
            return None
        return backup_path, output_path, report_type
def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Compare XML backup files and generate DiffReport',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  CVBackupCompare.exe
  CVBackupCompare.exe --backup-path "C:\\test"
  CVBackupCompare.exe --backup-path "D:\\Backup" --output "C:\\Reports"
        """
    )
    parser.add_argument(
        '--backup-path',
        type=str,
        default=r"\\admssim01\ADMS_DataEngineering\CompositeViewBackup",
        help='Base path to XML backup folders'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output folder for DiffReport CSV files'
    )
    parser.add_argument(
        '--report-type',
        type=str,
        choices=['composite', 'substation', 'both'],
        default='both',
        help='Type of report to generate'
    )
    return parser.parse_args()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = parse_arguments()
        backup_path = args.backup_path
        output_path = args.output
        report_type = args.report_type
    else:
        path_config = interactive_path_input()
        if path_config is None:
            sys.exit(0)
        backup_path, output_path, report_type = path_config
    if output_path is None:
        diffreport_folder = os.path.join(backup_path, "DiffReport")
    else:
        diffreport_folder = output_path
    print("\n" + "="*80)
    print("CONFIGURATION:")
    print("-" * 80)
    print(f"Backup base path: {backup_path}")
    print(f"DiffReport output folder: {diffreport_folder}")
    print(f"Report type: {report_type.upper()}")
    print("\nValidating paths...")
    if not os.path.exists(backup_path):
        print("="*80)
        print(f"✗ ERROR: Backup folder does not exist!")
        print(f"  Specified path: {backup_path}")
        print("="*80)
        input("\nPress ENTER to exit...")
        sys.exit(1)
    else:
        print(f"  ✓ Backup folder exists")
    print("="*80 + "\n")
    if report_type in ['composite', 'both']:
        compare_and_update("Composite", backup_path, diffreport_folder)
    if report_type in ['substation', 'both']:
        compare_and_update("Substation", backup_path, diffreport_folder)
    print("\n" + "="*80)
    print("✓ ALL REPORTS UPDATED SUCCESSFULLY!")
    print("="*80)
    print(f"\nOutput folder: {diffreport_folder}")
    input("\nPress ENTER to exit...")
 