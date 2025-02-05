import streamlit as st
import pandas as pd
import json
from urllib.parse import unquote
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import requests

def load_data(file_path):
    data = pd.read_csv(file_path)
    data['Date'] = pd.to_datetime(data['Date'], errors='coerce', dayfirst=True)
    return data

def safe_json_loads(json_str):
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None

def extract_levels(json_data, level_name):
    if json_data:
        for item in json_data:
            if item['name'] == level_name:
                return item['value']
    return None

def filter_farms(data):
    return sorted(data['farmName'].unique())

def exact_string_match(farm_name_param, farms):
    """
    Performs exact string matching for farm names
    """
    farm_name_param = farm_name_param.strip().lower()
    for farm in farms:
        if farm.strip().lower() == farm_name_param:
            return farm
    return None

def download_image(url, filename):
    try:
        img_response = requests.get(url)
        img_response.raise_for_status()
        
        img = Image.open(BytesIO(img_response.content))
        img_format = img.format if img.format else 'JPEG'
        if img_format not in ['JPEG', 'PNG', 'GIF']:
            img_format = 'JPEG'
        
        buf = BytesIO()
        img.save(buf, format=img_format)
        return buf.getvalue(), filename
    except (requests.exceptions.RequestException, UnidentifiedImageError) as e:
        st.error(f"Error downloading or processing image: {e}")
        return None, None

def display_farm_info(data, farm_name):
    images_to_download = []
    
    farm_data = data[data['farmName'] == farm_name]
    for index, row in farm_data.iterrows():
        col1, col2 = st.columns(2)
        with col1:
            # Add error handling for image display
            try:
                if pd.isna(row['Image URL']) or not isinstance(row['Image URL'], str):
                    st.warning(f"Invalid image URL for entry {index + 1}")
                    continue
                    
                # Try to fetch the image first to validate it
                response = requests.get(row['Image URL'])
                response.raise_for_status()  # This will raise an exception for bad status codes
                
                # Try to display the image - removed use_container_width parameter
                st.image(row['Image URL'], caption=f"Image {index + 1}")
                
                # Only proceed with download button if image is valid
                img_name = (f"{row['farmName']}_{row['Date'].strftime('%Y-%m-%d')}_{index + 1}.jpg" 
                           if isinstance(row['Date'], pd.Timestamp) 
                           else f"{row['farmName']}_unknown_date_{index + 1}.jpg")
                img_data, img_filename = download_image(row['Image URL'], img_name)
                if img_data:
                    st.download_button(label="Download Image", data=img_data, file_name=img_filename, mime="image/jpeg")
                    images_to_download.append((img_data, img_filename))
            except requests.exceptions.RequestException as e:
                st.error(f"Error loading image {index + 1}: {str(e)}")
            except Exception as e:
                st.error(f"Unexpected error displaying image {index + 1}: {str(e)}")
            
        with col2:
            st.write("Farm Name:", row['farmName'])
            st.write("Other Information:")
            try:
                if pd.isna(row['json data']):
                    st.warning("No JSON data available")
                else:
                    json_data = json.loads(row['json data'])
                    for item in json_data:
                        st.write(f"{item['name']}: {item['value']}")
            except json.JSONDecodeError:
                st.error("Invalid JSON data")
            except Exception as e:
                st.error(f"Error processing JSON data: {str(e)}")
            
            st.write("#### Activity ")
            st.write(row['activity_record'] if not pd.isna(row['activity_record']) else "No activity recorded")
            st.write('##### Activity Date')
            st.write(row['Date'] if not pd.isna(row['Date']) else "No date recorded")
    
    return images_to_download

def create_zip(images, zip_filename="images.zip"):
    from zipfile import ZipFile
    buf = BytesIO()
    with ZipFile(buf, 'w') as zipf:
        for img_data, img_filename in images:
            zipf.writestr(img_filename, img_data)
    buf.seek(0)
    return buf, zip_filename

def main():
    st.set_page_config(layout="wide")
    st.title("Farm Information Dashboard")
    
    data_url = "https://raw.githubusercontent.com/sakshamraj4/abinbev/main/test1.csv"
    try:
        data = load_data(data_url)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    # Add data validation
    required_columns = ['farmName', 'json data', 'Image URL', 'activity_record', 'Date']
    missing_columns = [col for col in required_columns if col not in data.columns]
    if missing_columns:
        st.error(f"Missing required columns: {', '.join(missing_columns)}")
        return
    
    # Clean the data
    data['json_data'] = data['json data'].apply(safe_json_loads)
    data = data.dropna(subset=['farmName'])  # Only drop rows with missing farm names
    data['Severity'] = data['json_data'].apply(lambda x: extract_levels(x, 'Severity'))

    farms = filter_farms(data)
    
    
    # Updated query parameter handling
    farm_name_param = st.query_params.get('farm_name', None)
    severity_param = st.query_params.get('severity', None)

    # Enhanced farm name matching
    if farm_name_param:
        farm_name_param = unquote(farm_name_param)
        matched_farm = exact_string_match(farm_name_param, farms)
        if matched_farm:
            default_farm_index = farms.index(matched_farm)
            st.success(f"Showing data for farm: {matched_farm}")
        else:
            st.warning(f"Farm '{farm_name_param}' not found. Showing default farm.")
            default_farm_index = 0
    else:
        default_farm_index = 0

    severity_levels = ['Select All'] + sorted(data['Severity'].dropna().unique())
    if severity_param and severity_param in severity_levels:
        default_severity_index = severity_levels.index(severity_param)
    else:
        default_severity_index = 0

    selected_farm = st.sidebar.selectbox(
        "Select Farm",
        farms,
        index=default_farm_index,
        key='farm_selector'
    )
    
    selected_severity = st.sidebar.selectbox(
        "Severity",
        severity_levels,
        index=default_severity_index,
        key='severity_selector'
    )

    if selected_farm:
        filtered_data = data[data['farmName'] == selected_farm]
        if selected_severity != 'Select All':
            filtered_data = filtered_data[filtered_data['Severity'] == selected_severity]

        if filtered_data.empty:
            st.warning("No data available for the selected filters.")
        else:
            images_to_download = display_farm_info(filtered_data, selected_farm)
            if images_to_download:
                zip_data, zip_filename = create_zip(images_to_download)
                st.sidebar.download_button(
                    label="Download All Images",
                    data=zip_data,
                    file_name=zip_filename,
                    mime="application/zip"
                )

if __name__ == "__main__":
    main()
