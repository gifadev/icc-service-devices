import pyshark
import re
import json
import time
from database_config import connect_to_database
from broadcaster import schedule_update_broadcast 
import logging

logging.basicConfig(
    level=logging.INFO,  
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("icc.log"), 
        logging.StreamHandler() 
    ]
)

logger = logging.getLogger(__name__) 


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
        ('510', '22'): 'Indosat',
        ('510', '20'): 'TelkomFlexi',  
        ('510', '27'): 'Net 1',
        ('510', '28'): 'Smartfren',
        ('510', '78'): 'Hinet',
        ('510', '88'): 'BOLT',
        ('510', '89'): '3',
        ('510', '99'): 'Esia',
    }
    return operator_db.get((mcc, mnc), 'Unknown Operator')

def extract_gsm_data(cleaned_structure):
    logger.debug("Start Extract GSM Data")
    data = {}

    # Ekstraksi MCC dan MNC
    mcc_mnc_pattern = r'Mobile Country Code \(MCC\): [\w\s]+\((\d+)\).*?Mobile Network Code \(MNC\): [\w\s-]+\((\d+)\)'
    mcc_mnc_matches = re.search(mcc_mnc_pattern, cleaned_structure)
    if mcc_mnc_matches:
        data['MCC'] = mcc_mnc_matches.group(1)
        data['MNC'] = mcc_mnc_matches.group(2)
        data['operator'] = get_operator_name(data['MCC'], data['MNC'])
    

    # Location Area Code
    lac_pattern = r'Location Area Code \(LAC\): (0x[0-9a-fA-F]+)'
    lac_matches = re.search(lac_pattern, cleaned_structure)
    if lac_matches:
        lac = lac_matches.group(1)
        print(lac)
        data['Local Area Code'] = int(lac, 16) if lac != "-" and isinstance(lac, str) else lac

    
    # ARFCN
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
        bounds = re.findall(r'-?\d+', range_str)
        if len(bounds) == 2:
            lower = int(bounds[0])
            upper = int(bounds[1])
            mid_value = (lower + upper) / 2
            data['RXLEV-ACCESS-MIN'] = mid_value

    # Ekstraksi Cell Reselect Offset
    cell_reselect_offset_pattern = r'Cell Reselect Offset:\s*([-0-9]+)\s*dB'
    cell_reselect_offset_matches = re.search(cell_reselect_offset_pattern, cleaned_structure)
    if cell_reselect_offset_matches:
        data['Cell Reselect Offset'] = int(cell_reselect_offset_matches.group(1))

    # Ekstraksi Temporary Offset
    temporary_offset_pattern = r'Temporary Offset:\s*([-0-9]+)\s*dB'
    temporary_offset_matches = re.search(temporary_offset_pattern, cleaned_structure)
    if temporary_offset_matches:
        data['Temporary Offset'] = int(temporary_offset_matches.group(1))

    # Ekstraksi Penalty Time
    penalty_time_pattern = r'Penalty Time:\s*([0-9]+)\s*s'
    penalty_time_matches = re.search(penalty_time_pattern, cleaned_structure)
    if penalty_time_matches:
        data['Penalty Time'] = int(penalty_time_matches.group(1))

    # Ekstraksi T3212
    t3212_pattern = r'T3212:\s*([0-9]+)'
    t3212_matches = re.search(t3212_pattern, cleaned_structure)
    if t3212_matches:
        data['T3212'] = int(t3212_matches.group(1))

    # Ekstraksi SI2quater Indicator
    si2quater_pattern = r'SI2quater Indicator:\s*(\w+)'
    si2quater_matches = re.search(si2quater_pattern, cleaned_structure)
    if si2quater_matches:
        indicator_value = si2quater_matches.group(1)
        data['SI2quater Indicator'] = True if indicator_value.lower() == 'present' else False


    return data

def extract_lte_data(cleaned_structure):
    logger.debug("Start Extract LTE Data")
    data = {}

    # MCC dan MNC
    mcc_mnc_pattern = r'MCC-MNC-Digit:\s*(\d+)'
    mcc_mnc_matches = re.findall(mcc_mnc_pattern, cleaned_structure)
    if mcc_mnc_matches:
        mcc = ''.join(mcc_mnc_matches[:3])
        mnc = ''.join(mcc_mnc_matches[3:5])
        data['MCC'] = mcc
        data['MNC'] = mnc
        data['operator'] = get_operator_name(mcc, mnc)

    # ARFCN
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

    # Signal Level
    signal_level_pattern = r'Signal Level:\s*([-\d]+)\s*dBm'
    signal_level_matches = re.findall(signal_level_pattern, cleaned_structure)
    if signal_level_matches:
        data['signal_level'] = int(signal_level_matches[0])
    
    # Signal/Noise Ratio (SNR)
    snr_pattern = r'Signal/Noise Ratio:\s*([-\d]+)\s*dB'
    snr_match = re.search(snr_pattern, cleaned_structure)
    if snr_match:
        data['snr'] = int(snr_match.group(1))

    # q-RxLevMin
    rxlevelmin_pattern = r'q-RxLevMin:\s*(-?\d+dBm\s*\(-?\d+\))'
    rxlevelmin_matches = re.findall(rxlevelmin_pattern, cleaned_structure)
    if rxlevelmin_matches:
        rxlevelmin_str = rxlevelmin_matches[0]
        inner_match = re.search(r'\((-?\d+)\)', rxlevelmin_str)
        if inner_match:
            data['Rx Level Min'] = int(inner_match.group(1))

    # p-Max
    p_max_pattern = r'p-Max:\s*(-?\d+)'
    p_max_matches = re.search(p_max_pattern, cleaned_structure)
    if p_max_matches:
        data['p-Max'] = int(p_max_matches.group(1))

    # SI Info Value changed
    si_info_pattern = r'SI Info Value changed:\s*(\w+)'
    si_info_matches = re.search(si_info_pattern, cleaned_structure)
    if si_info_matches:
        data['SI Info Value changed'] = si_info_matches.group(1)

    # sib-MappingInfo
    sib_mapping_pattern = r'sib-MappingInfo:\s*(\d+)'
    sib_mapping_matches = re.findall(sib_mapping_pattern, cleaned_structure)
    if sib_mapping_matches:
        data['sib-MappingInfo'] = [int(item) for item in sib_mapping_matches]

    # nonCriticalExtension
    non_critical_extension_pattern = r'nonCriticalExtension:\s*(\w+)'
    non_critical_extension_matches = re.search(non_critical_extension_pattern, cleaned_structure)
    if non_critical_extension_matches:
        data['nonCriticalExtension'] = non_critical_extension_matches.group(1)

    # plmn-IdentityList
    plmn_identity_list_pattern = r'plmn-IdentityList:\s*(\d+)'
    plmn_identity_list_matches = re.findall(plmn_identity_list_pattern, cleaned_structure)
    if plmn_identity_list_matches:
        data['plmn-IdentityList'] = [int(item) for item in plmn_identity_list_matches]

    # Security Header Type
    security_header_type_pattern = r'Security header type:\s*(\w+)'
    security_header_type_matches = re.search(security_header_type_pattern, cleaned_structure)
    if security_header_type_matches:
        if security_header_type_matches.group(1) == 'Plain':
            data['Status'] = False

    return data


global_cap = None

def map_arfcn(arfcn):
    if 1 <= arfcn <= 124:
        return "2G GSM 900"
    elif 512 <= arfcn <= 885:
        return "2G GSM 1800"
    elif 10562 <= arfcn <= 10838:
        return "3G UMTS Band 1 (2100 MHz)"
    elif 2937 <= arfcn <= 3088:
        return "3G UMTS Band 8 (900 MHz)"
    elif 0 < arfcn <= 599:
        return "4G LTE Band 1 (2100 MHz)"
    elif 1200 <= arfcn <= 1949:
        return "4G LTE Band 3 (1800 MHz)"
    elif 36200 <= arfcn <= 36349:
        return "4G LTE Band 8 (900 MHz)"
    elif 37750 <= arfcn <= 38249:
        return "4G LTE Band 5 (850 MHz)"
    elif 28540 <= arfcn <= 28639:
        return "4G LTE Band 28 (700 MHz)"
    elif 38500 <= arfcn <= 40000:
        return "4G LTE Band 40 ( MHz)"
    # elif 42590 <= arfcn <= 43589:
    #     return "4G LTE Band 40 (2300 MHz)"
    else:
        return "Unknown / Out of Indonesia bands"

# Fungsi utama untuk menangkap live data
def start_live_capture():
    global global_cap

    output_file_gsm = 'test_gsm_data.json'   # Menyimpan data GSM di sini
    output_file_umts = 'test_umts_data.json' # Menyimpan data UMTS di sini
    output_file_lte = 'test_lte_data.json'   # Menyimpan data LTE di sini
    
    existing_data_gsm = []
    existing_data_umts = []
    existing_data_lte = []
    packet_count = 0
    start_time = time.time()
    
    interface = 'lo'  # Gunakan interface sesuai kebutuhan

    try:
        cap = pyshark.LiveCapture(interface=interface)
        global_cap = cap 
        logger.info(f"Memulai live capture di interface '{interface}'")
    except Exception as e:
        logger.error(f"Error initializing live capture on interface '{interface}': {e}")
        return
    
    try:
        cap.set_debug()
        for packet in cap.sniff_continuously():
            full_packet_structure = str(packet)
            cleaned_structure = remove_ansi_escape_codes(full_packet_structure)
            cleaned_structure = clean_packet_structure(cleaned_structure)

            # Parsing tipe paket
            payload_type_matches = re.findall(r'Payload Type:\s*(\w+)', cleaned_structure)
            protocol_type_matches = re.findall(r'Protocol:\s*(\w+)', cleaned_structure)
            arfcn_type_matches = re.findall(r'ARFCN:\s*(\d+)', cleaned_structure)
            
            if arfcn_type_matches:
                arfcn = int(arfcn_type_matches[0])
                arfcn_band = map_arfcn(arfcn)
                print(f"ARFCN {arfcn} → {arfcn_band}")

                # Menyimpan data sesuai dengan band
                if "GSM" in arfcn_band:
                    existing_data_gsm.append({'arfcn': arfcn, 'band': arfcn_band})
                elif "UMTS" in arfcn_band:
                    existing_data_umts.append({'arfcn': arfcn, 'band': arfcn_band})
                elif "LTE" in arfcn_band:
                    existing_data_lte.append({'arfcn': arfcn, 'band': arfcn_band})

            # Simpan data setiap 10 paket atau setiap 60 detik
            if packet_count % 10 == 0 or (time.time() - start_time) >= 60:
                with open(output_file_gsm, 'w') as f:
                    json.dump(existing_data_gsm, f, indent=4)
                with open(output_file_umts, 'w') as f:
                    json.dump(existing_data_umts, f, indent=4)
                with open(output_file_lte, 'w') as f:
                    json.dump(existing_data_lte, f, indent=4)
                
                # logger.info(f"Data GSM, UMTS, dan LTE disimpan ke database setelah {packet_count} paket.")
                start_time = time.time()

    except Exception as e:
        logger.exception(f"Error saat menangkap paket: {e}")
    finally:
        try:
            logger.info("Menutup live capture...")
            cap.close()
            logger.info("Live capture dihentikan dengan sukses.")
        except Exception as e:
            logger.error(f"Error saat menutup live capture: {e}")
        global_cap = None

if __name__ == "__main__":
    start_live_capture()
