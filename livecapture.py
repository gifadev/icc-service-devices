import pyshark
import re
import json
import time
from database_config import connect_to_database
import pyshark.tshark.tshark


def remove_ansi_escape_codes(text):
    """Remove ANSI escape codes used for terminal coloring or formatting."""
    ansi_escape = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def clean_packet_structure(text):
    """Clean the packet structure by removing unnecessary spaces and line breaks."""
    text = re.sub(r'\t+', ' ', text)
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def get_operator_name(mcc, mnc):
    """Get operator name based on MCC and MNC."""
    operator_db = {
        ('510', '00'): 'ACeS',
        ('510', '01'): 'Indosat', 
        ('510', '03'): 'StarOne',
        ('510', '07'): 'TelkomFlexi', 
        ('510', '08'): 'Axis',
        ('510', '09'): 'Smartfren',
        ('510', '10'): 'Telkomsel',
        ('510', '11'): 'XL',
        ('510', '21'): 'Indosat', 
        ('510', '20'): 'TelkomFlexi',  
        ('510', '27'): 'Net 1',
        ('510', '28'): 'Smartfren',
        ('510', '78'): 'Hinet',
        ('510', '88'): 'BOLT',
        ('510', '99'): 'Esia',
    }
    return operator_db.get((mcc, mnc), 'Unknown Operator')

def extract_gsm_data(cleaned_structure):
    """Extract GSM data from cleaned packet structure."""
    data = {}

    # MCC and MNC 
    mcc_mnc_pattern = r'Mobile Country Code \(MCC\): [\w\s]+\((\d+)\).*?Mobile Network Code \(MNC\): [\w\s-]+\((\d+)\)'
    mcc_mnc_matches = re.search(mcc_mnc_pattern, cleaned_structure)
    if mcc_mnc_matches:
        data['MCC'] = mcc_mnc_matches.group(1)
        data['MNC'] = mcc_mnc_matches.group(2)
        data['operator'] = get_operator_name(data['MCC'], data['MNC'])

    # LAC (Location Area Code)
    lac_pattern = r'Location Area Code \(LAC\): (0x[0-9a-fA-F]+)'
    lac_matches = re.search(lac_pattern, cleaned_structure)
    if lac_matches:
        lac = lac_matches.group(1)
        data['Local Area Code'] = int(lac, 16) if lac != "-" and isinstance(lac, str) else lac

    # ARFCN (Absolute Radio Frequency Channel Number)
    arfcn_pattern = r'ARFCN:\s*(\d+)'
    arfcn_matches = re.search(arfcn_pattern, cleaned_structure)
    if arfcn_matches:
        data['ARFCN'] = int(arfcn_matches.group(1))

    # Cell Identity (CI)
    ci_pattern = r'Cell CI: (0x[0-9a-fA-F]+)'
    ci_matches = re.search(ci_pattern, cleaned_structure)
    if ci_matches:
        ci = ci_matches.group(1)
        data['Cell Identity'] = int(ci, 16) if ci != "-" and isinstance(ci, str) else ci

    # Signal Level (RxLev)
    rxlev_pattern = r'Signal Level:\s*(-?\d+)\s*dBm'
    rxlev_matches = re.search(rxlev_pattern, cleaned_structure)
    if rxlev_matches:
        data['RxLev'] = int(rxlev_matches.group(1))


    # RXLEV-ACCESS-MIN
    rxlev_access_min_pattern = r'RXLEV-ACCESS-MIN:\s*(-?\d+\s*<=\s*x\s*<\s*-?\d+)\s*dBm'
    rxlev_access_min_matches = re.search(rxlev_access_min_pattern, cleaned_structure)
    if rxlev_access_min_matches:
        range_str = rxlev_access_min_matches.group(1)
        # Ekstrak kedua angka dari string
        bounds = re.findall(r'-?\d+', range_str)
        if len(bounds) == 2:
            lower = int(bounds[0])
            upper = int(bounds[1])
            print(lower)
            print(upper)
            mid_value = (lower + upper) / 2
            data['RXLEV-ACCESS-MIN'] = mid_value
            

    # # Cell Reselection Hysteresis
    # hysteresis_pattern = r'Cell Reselection Hysteresis:\s*(\d+)'
    # hysteresis_matches = re.search(hysteresis_pattern, cleaned_structure)
    # if hysteresis_matches:
    #     data['Cell Reselection Hysteresis'] = int(hysteresis_matches.group(1))

    # # Channel Type
    # channel_type_pattern = r'Channel Type:\s*(\w+)'
    # channel_type_matches = re.search(channel_type_pattern, cleaned_structure)
    # if channel_type_matches:
    #     data['Channel Type'] = channel_type_matches.group(1)

    # # GPRS Indicator
    # gprs_pattern = r'GPRS Indicator:\s*(\w+)'
    # gprs_matches = re.search(gprs_pattern, cleaned_structure)
    # if gprs_matches:
    #     data['GPRS Indicator'] = gprs_matches.group(1)

    # True Or Fake BTS
    data['Status'] = True
    security_header_type_patteren = r'Security header type:\s*(\w+)'
    security_header_type_matches = re.search(security_header_type_patteren, cleaned_structure)
    if security_header_type_matches:
        # print(security_header_type_matches[0])
        if security_header_type_matches  == 'Plain':
            data['Status'] = False

    return data

def extract_lte_data(cleaned_structure):
    """Extract LTE data from cleaned packet structure."""
    data = {}

    # MCC and MNC
    mcc_mnc_pattern = r'MCC-MNC-Digit:\s*(\d+)'
    mcc_mnc_matches = re.findall(mcc_mnc_pattern, cleaned_structure)
    if mcc_mnc_matches:
        mcc = ''.join(mcc_mnc_matches[:3])
        mnc = ''.join(mcc_mnc_matches[3:5])
        data['MCC'] = mcc
        data['MNC'] = mnc
        data['operator'] = get_operator_name(mcc, mnc)

    # ARFCN (Absolute Radio Frequency Channel Number)
    arfcn_pattern = r'ARFCN:\s*(\d+)'
    arfcn_matches = re.search(arfcn_pattern, cleaned_structure)
    if arfcn_matches:
        data['ARFCN'] = int(arfcn_matches.group(1))

    # Cell Identity
    cell_identity_pattern = r'cellIdentity:\s*([0-9a-fA-F]+)'
    cell_identity_matches = re.findall(cell_identity_pattern, cleaned_structure)
    if cell_identity_matches:
        ci = cell_identity_matches[0]
        data['Cell Identity'] = int(ci, 16) if ci != "-" and isinstance(ci, str) else ci

    # Tracking Area Code
    tracking_area_pattern = r'trackingAreaCode:\s*([0-9a-fA-F]+)'
    tracking_area_matches = re.findall(tracking_area_pattern, cleaned_structure)
    if tracking_area_matches:
        tac = tracking_area_matches[0]
        data['Tracking Area Code'] = int(tac, 16) if tac != "-" and isinstance(tac, str) else tac

    # Frequency Band Indicator
    freq_band_pattern = r'freqBandIndicator:\s*(\d+)'
    freq_band_matches = re.findall(freq_band_pattern, cleaned_structure)
    if freq_band_matches:
        data['Frequency Band Indicator'] = int(freq_band_matches[0])

    signal_level_pattern = r'Signal Level:\s*([-\d]+)\s*dBm'
    signal_level_matches = re.findall(signal_level_pattern, cleaned_structure)
    if signal_level_matches:
        data['signal_level'] = int(signal_level_matches[0])

    # RxLevMin
    rxlevelmin_pattern = r'q-RxLevMin:\s*(-?\d+dBm\s*\(-?\d+\))'
    rxlevelmin_matches = re.findall(rxlevelmin_pattern, cleaned_structure)
    if rxlevelmin_matches:
        # data['Rx Level Min'] = rxlevelmin_matches[0]
        rxlevelmin_str = rxlevelmin_matches[0] 
        # Ambil angka di dalam tanda kurung
        inner_match = re.search(r'\((-?\d+)\)', rxlevelmin_str)
        if inner_match:
            data['Rx Level Min'] = int(inner_match.group(1))
            
        # outer_match = re.search(r'(-?\d+)dBm', rxlevelmin_str)
        # if outer_match:
        #     data['Rx Level Min'] = int(outer_match.group(1))

    signal_noise_ratio = r'Signal Level:\s*([-\d]+)\s*dBm'
    signal_noise_ratio_matches = re.findall(signal_noise_ratio, cleaned_structure)
    if signal_noise_ratio_matches:
        data['snr'] = int(signal_noise_ratio_matches[0])

    # # Scheduling Info
    # scheduling_info_pattern = r'schedulingInfoList:\s*\d+\s*items\s*SchedulingInfo\s*(\S+)'
    # scheduling_info_matches = re.findall(scheduling_info_pattern, cleaned_structure)
    # if scheduling_info_matches:
    #     data['Scheduling Info'] = ', '.join(scheduling_info_matches)

    # # IMS Emergency Support
    # ims_support_pattern = r'ims-EmergencySupport-r9:\s*(\w+)'
    # ims_support_matches = re.findall(ims_support_pattern, cleaned_structure)
    # if ims_support_matches:
    #     data['IMS Emergency Support'] = ims_support_matches[0]

    # # q-RxLevMin
    # q_rxlev_pattern = r'q-RxLevMin:\s*([-\d]+)dBm'
    # q_rxlev_matches = re.findall(q_rxlev_pattern, cleaned_structure)
    # if q_rxlev_matches:
    #     data['q-RxLevMin'] = q_rxlev_matches[0]

    # # si-WindowLength
    # si_window_length_pattern = r'si-WindowLength:\s*([^\(]+)\s*\(\d+\)'
    # si_window_length_matches = re.findall(si_window_length_pattern, cleaned_structure)
    # if si_window_length_matches:
    #     data['si-WindowLength'] = si_window_length_matches[0]

    # True Or Fake BTS
    data['Status'] = True
    security_header_type_patteren = r'Security header type:\s*(\w+)'
    security_header_type_matches = re.search(security_header_type_patteren, cleaned_structure)
    if security_header_type_matches:
        security_header_type = security_header_type_matches.group(1)
        if security_header_type == 'Plain':
            data['Status'] = False  

    return data


def create_campaign():
    connection = connect_to_database()
    if connection is None:
        return None
    
    cursor = connection.cursor()
    
    sql = "INSERT INTO campaign (timestamp) VALUES (DATETIME('now'))"
    cursor.execute(sql)
    
    campaign_id = cursor.lastrowid 
    
    connection.commit()
    cursor.close()
    connection.close()
    
    return campaign_id


def save_gsm_data_to_db(gsm_data, campaign_id):
    # Hubungkan ke database
    connection = connect_to_database()
    cursor = connection.cursor()
    
    # Loop melalui setiap data GSM
    for data in gsm_data:
        # Ambil nilai-nilai penting dari data GSM
        mcc = data.get('MCC')  
        mnc = data.get('MNC')  
        local_area_code = data.get('Local Area Code')  
        cell_identity = data.get('Cell Identity')  
        arfcn = data.get('ARFCN')  

        # Kasus 2: Data memiliki MCC, MNC, Local Area Code, dan Cell Identity
        if (mcc is not None and mcc != '') and (mnc is not None and mnc != '') and \
           (local_area_code is not None and local_area_code != '') and \
           (cell_identity is not None and cell_identity != ''):

            # Cek apakah data dengan kombinasi MCC, MNC, Local Area Code, dan Cell Identity sudah ada
            check_sql = """
            SELECT id FROM gsm 
            WHERE mcc = ? AND mnc = ? AND local_area_code = ? AND cell_identity = ? AND id_campaign = ?
            """
            cursor.execute(check_sql, (mcc, mnc, local_area_code, cell_identity, campaign_id))
            results = cursor.fetchall()
            
            # Jika data belum ada, lakukan INSERT
            if not results:
                sql = """
                INSERT INTO gsm (mcc, mnc, operator, local_area_code, arfcn, cell_identity, rxlev, status, id_campaign)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                values = (
                    data.get('MCC'),
                    data.get('MNC'),
                    data.get('operator'),
                    data.get('Local Area Code'),
                    data.get('ARFCN'),
                    data.get('Cell Identity'),
                    data.get('RxLev'),
                    data.get('Status'),
                    campaign_id 
                )
                cursor.execute(sql, values)

        # Kasus 3: MCC dan MNC kosong, tetapi Status memiliki nilai
        elif (mcc is None or mcc == '') and (mnc is None or mnc == '') and data.get('Status') is not None:
            # Cari data di database yang memiliki ARFCN yang sama untuk campaign ini
            select_sql = """
            SELECT id FROM gsm WHERE arfcn = ? AND id_campaign = ?
            """
            cursor.execute(select_sql, (data.get('ARFCN'), campaign_id))
            results = cursor.fetchall()
            
            # Jika ditemukan data dengan ARFCN yang sama, update status
            if results:
                update_sql = """
                UPDATE gsm SET status = ? WHERE arfcn = ? AND id_campaign = ?
                """
                cursor.execute(update_sql, (data.get('Status'), data.get('ARFCN'), campaign_id))
    
    # Commit perubahan ke database
    connection.commit()
    # Tutup kursor dan koneksi
    cursor.close()
    connection.close()


# Fungsi untuk menyimpan data LTE ke database
def save_lte_data_to_db(lte_data, campaign_id):
    # Hubungkan ke database
    connection = connect_to_database()
    cursor = connection.cursor()
    
    # Loop melalui setiap data LTE
    for data in lte_data:
        # Ambil nilai-nilai penting dari data LTE
        mcc = data.get('MCC')  # Mobile Country Code
        mnc = data.get('MNC')  # Mobile Network Code
        status = data.get('Status')  # Status sel
        arfcn = data.get('ARFCN')  # Absolute Radio Frequency Channel Number
        cell_identity = data.get('Cell Identity')  # Identitas sel
        tracking_area_code = data.get('Tracking Area Code')  # Kode area pelacakan
        frequency_band_indicator = data.get('Frequency Band Indicator')  # Indikator band frekuensi
        signal_level = data.get('signal_level')  # Tingkat sinyal
        snr = data.get('snr')  # Signal-to-Noise Ratio
        
        # Kasus 1: Data memiliki MCC, MNC, TAC, dan Cell Identity
        if (mcc is not None and mcc != '') and (mnc is not None and mnc != '') and \
           (tracking_area_code is not None and tracking_area_code != '') and \
           (cell_identity is not None and cell_identity != ''):
            
            # Cek apakah data dengan kombinasi MCC, MNC, TAC, dan Cell Identity sudah ada di database untuk campaign ini
            check_sql = """
            SELECT id FROM lte 
            WHERE mcc = ? AND mnc = ? AND tracking_area_code = ? AND cell_identity = ? AND id_campaign = ?
            """
            cursor.execute(check_sql, (mcc, mnc, tracking_area_code, cell_identity, campaign_id))
            results = cursor.fetchall()
            
            # Jika data belum ada, lakukan INSERT
            if not results:
                sql = """
                INSERT INTO lte (mcc, mnc, operator, arfcn, cell_identity, tracking_area_code, frequency_band_indicator, 
                                 signal_level, snr, status, id_campaign)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                values = (
                    mcc,
                    mnc,
                    data.get('operator'),
                    arfcn,
                    cell_identity,
                    tracking_area_code,
                    frequency_band_indicator,
                    signal_level,
                    snr,
                    status,
                    campaign_id  # Sertakan ID campaign
                )
                cursor.execute(sql, values)
        
        # Kasus 2: MCC dan MNC kosong, tetapi Status memiliki nilai
        elif (mcc is None or mcc == '') and (mnc is None or mnc == '') and status is not None:
            # Cari data di database yang memiliki ARFCN yang sama untuk campaign ini
            select_sql = """
            SELECT id FROM lte WHERE arfcn = ? AND id_campaign = ?
            """
            cursor.execute(select_sql, (arfcn, campaign_id))
            results = cursor.fetchall()
            
            # Jika ditemukan data dengan ARFCN yang sama, update status
            if results:
                update_sql = """
                UPDATE lte SET status = ? WHERE arfcn = ? AND id_campaign = ?
                """
                cursor.execute(update_sql, (status, arfcn, campaign_id))
    
    # Commit perubahan ke database
    connection.commit()
    # Tutup kursor dan koneksi
    cursor.close()
    connection.close()


def start_live_capture(stop_event, campaign_id):
    output_file_gsm = 'gsm_data.json'
    output_file_lte = 'lte_data.json'
    
    existing_data_gsm = []
    existing_data_lte = []

    packet_count = 0
    start_time = time.time()
    
    interface = 'lo'
    try:
        cap = pyshark.LiveCapture(interface=interface)
    except (pyshark.capture.capture.TSharkNotFoundError, OSError) as e:
        print(f"Error: Interface '{interface}' tidak ditemukan atau TShark tidak terinstal.")
        return
    
    try:
        # Set timeout pada capture untuk check stop_event lebih sering
        cap.set_debug()
        for packet in cap.sniff_continuously(packet_count=0):
            if stop_event.is_set():
                print("Stop signal received in capture thread, shutting down...")
                break
                
            full_packet_structure = str(packet)
            cleaned_structure = remove_ansi_escape_codes(full_packet_structure)
            cleaned_structure = clean_packet_structure(cleaned_structure)

            payload_type_pattern = r'Payload Type:\s*(\w+)'
            payload_type_matches = re.findall(payload_type_pattern, cleaned_structure)
            protocol_type_pattern = r'Protocol:\s*(\w+)'
            protocol_type_matches = re.findall(protocol_type_pattern, cleaned_structure)
            arfcn_type_pattern = r'ARFCN:\s*(\d+)'
            arfcn_type_matches = re.findall(arfcn_type_pattern, cleaned_structure)
            
            if payload_type_matches:
                payload_type = payload_type_matches[0] 
                protocol_type = protocol_type_matches[0]
                arfcn_type = arfcn_type_matches[0]
                
                if protocol_type == 'UDP':
                    if payload_type == 'GSM':
                        gsm_data = extract_gsm_data(cleaned_structure)
                        if gsm_data:
                            print(gsm_data)
                            existing_data_gsm.append(gsm_data)
                    elif payload_type == 'LTE' and arfcn_type != '0':
                        lte_data = extract_lte_data(cleaned_structure)
                        if lte_data:
                            print(lte_data)
                            existing_data_lte.append(lte_data)
            
            packet_count += 1
            if packet_count % 10 == 0 or (time.time() - start_time) >= 60:
                with open(output_file_gsm, 'w') as f:
                    json.dump(existing_data_gsm, f, indent=4)
                with open(output_file_lte, 'w') as f:
                    json.dump(existing_data_lte, f, indent=4)
                
                save_gsm_data_to_db(existing_data_gsm, campaign_id)
                save_lte_data_to_db(existing_data_lte, campaign_id)
                
                print(f"Data saved at packet {packet_count}")
                start_time = time.time()
                existing_data_gsm = []
                existing_data_lte = []

    except Exception as e:
        print(f"Error in capture: {e}")
    finally:
        try:
            print("Cleaning up capture resources...")
            cap.close()
            print("Capture cleaned up successfully")
        except Exception as e:
            print(f"Error during cleanup: {e}")
