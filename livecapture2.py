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
        ('510', '20'): 'TelkomFlexi',  
        ('510', '27'): 'Net 1',
        ('510', '28'): 'Smartfren',
        ('510', '78'): 'Hinet',
        ('510', '88'): 'BOLT',
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

def score_packet_gsm(data):
    score = 0
    details = [] 

    # 1. SI2quater Indicator: jika Present dianggap positif
    if data.get("SI2quater Indicator") is True:
        score += 0  # Sesuaikan perhitungan dengan kode 2
        details.append("SI2quater Indicator Present: +0")
    else:
        score += 20  # Skor penalti jika tidak ada
        details.append("SI2quater Indicator tidak Present: +20")

    # 2. T3212:
    t3212 = data.get("T3212")
    if t3212 is not None:
        if t3212 <= 0:
            score += 20
            details.append("T3212 <= 0: +20")
        elif t3212 < 30:
            score += ((30 - t3212) / 30) * 20
            details.append(f"T3212 < 30, Skor proporsional: +{((30 - t3212) / 30) * 20}")
        else:
            score += 0
            details.append("T3212 >= 30: +0")
    else:
        details.append("T3212 tidak ada: +20")
        score += 20

    # 3. Cell Reselect Offset
    cell_reselect = data.get("Cell Reselect Offset")
    if cell_reselect is not None:
        if cell_reselect <= 115:
            score += 0
            details.append("Cell Reselect Offset <= 115: +0")
        elif cell_reselect >= 130:
            score += 40
            details.append("Cell Reselect Offset >= 130: +40")
        else:
            score += ((cell_reselect - 115) / 15) * 40
            details.append(f"Cell Reselect Offset antara 115 dan 130, Skor proporsional: +{((cell_reselect - 115) / 15) * 40}")
    else:
        details.append("Cell Reselect Offset tidak ada: +40")
        score += 40

    # 4. RXLEV-ACCESS-MIN
    rxlev_access = data.get("RXLEV-ACCESS-MIN")
    if rxlev_access is not None:
        if rxlev_access > -105:
            score += 0
            details.append("RXLEV-ACCESS-MIN > -105: +0")
        elif rxlev_access <= -110:
            score += 40
            details.append("RXLEV-ACCESS-MIN <= -110: +40")
        else:
            score += ((-105 - rxlev_access) / 5) * 40
            details.append(f"RXLEV-ACCESS-MIN antara -105 dan -110, Skor proporsional: +{((-105 - rxlev_access) / 5) * 40}")
    else:
        details.append("RXLEV-ACCESS-MIN tidak ada: +40")
        score += 40

    total_risk = score

    cro_score = 0
    if cell_reselect is not None:
        if cell_reselect <= 115:
            cro_score = 0
        elif cell_reselect >= 130:
            cro_score = 40
        else:
            cro_score = ((cell_reselect - 115) / 15) * 40

    threshold = 60 
    is_fake = (cro_score < 40) and (total_risk > threshold)

    details.append(f"CRO Score: {cro_score}")
    details.append(f"Total Risk: {total_risk}")
    details.append(f"Is Fake: {is_fake}")

    # Menambahkan ke hasil
    data['is_fake'] = is_fake

    return score, details

def score_packet_lte(cleaned_structure):
    score = 0
    reasons = [] 

    # Cek apakah "plmn-IdentityList" ada dan memiliki lebih dari 1 item
    if "plmn-IdentityList: 2 items" in cleaned_structure:
        score += 1                                                                                            
        reasons.append("Multiple PLMN Identity entries")
    
    # Cek apakah "SI Info Value changed" ada dalam paket
    if "SI Info Value changed" in cleaned_structure:
        score += 1
        reasons.append("System Info Value Tag change warning")
    
    # Cek apakah "sib-MappingInfo" ada dengan 0 atau 3 item
    if "sib-MappingInfo: 0 items" in cleaned_structure or "sib-MappingInfo: 3 items" in cleaned_structure:
        score += 1
        reasons.append("Irregular SIB Mapping count")
    
    # if "q-RxLevMin: -140dBm" in cleaned_structure:
    #     score += 1
    #     reasons.append("Suspicious q-RxLevMin value")

    # Cek apakah ada "p-Max" dalam paket
    if "p-Max" in cleaned_structure:
        score += 1
        reasons.append("Presence of p-Max field")
    
    # Cek apakah ada "nonCriticalExtension" dalam paket
    if "nonCriticalExtension" in cleaned_structure:
        score += 1
        reasons.append("Existence of nonCriticalExtension field")
    
    return score, reasons

def evaluate_packet_gsm(cleaned_structure):
    data = extract_gsm_data(cleaned_structure)
    score, details = score_packet_gsm(data)
    status = True if not data.get("is_fake") else False
    arfcn = data.get('ARFCN')
    if arfcn != 0:
        result = {
            "MCC": data.get("MCC"),
            "MNC": data.get("MNC"),
            "operator": data.get("operator"),
            "ARFCN": data.get("ARFCN"),
            'Local Area Code': data.get("Local Area Code"),
            "Cell Identity": data.get("Cell Identity"),
            "RxLev": data.get("RxLev"),
            "RXLEV-ACCESS-MIN": data.get("RXLEV-ACCESS-MIN"),
            "Cell Reselect Offset": data.get("Cell Reselect Offset"),
            "Temporary Offset": data.get("Temporary Offset"),
            "Penalty Time": data.get("Penalty Time"),
            "T3212": data.get("T3212"),
            "SI2quater Indicator": data.get("SI2quater Indicator"),
            "score": score,
            "status": status
        }
        # print(json.dumps(result, indent=4))
        return result

def evaluate_packet_lte(cleaned_structure):
    extracted_data = extract_lte_data(cleaned_structure)  
    score, reasons = score_packet_lte(cleaned_structure)
    threshold = 3
    is_fake = score >= threshold
    status = True if not is_fake else False
    arfcn = extracted_data.get('ARFCN')
    if arfcn != 0:
        result = {
            'MCC': extracted_data.get('MCC', 'N/A'),
            'MNC': extracted_data.get('MNC', 'N/A'),
            "operator": extracted_data.get("operator", 'N/A'),
            'ARFCN': extracted_data.get('ARFCN', 'N/A'),
            'Signal Level': extracted_data.get('signal_level', 'N/A'),
            'snr': extracted_data.get('snr', 'N/A'),
            'Cell Identity': extracted_data.get('Cell Identity', 'N/A'),
            'Tracking Area Code': extracted_data.get('Tracking Area Code', 'N/A'),
            'Frequency Band Indicator': extracted_data.get('Frequency Band Indicator', 'N/A'),
            'Rx Level Min': extracted_data.get('Rx Level Min', 'N/A'),
            'p-Max': extracted_data.get('p-Max', 'N/A'),
            'SI Info Value changed': extracted_data.get('SI Info Value changed', 'N/A'),
            'sib-MappingInfo': extracted_data.get('sib-MappingInfo', 'N/A'),
            'nonCriticalExtension': extracted_data.get('nonCriticalExtension', 'N/A'),
            'plmn-IdentityList': extracted_data.get('plmn-IdentityList', 'N/A'),
            'Score': score,
            'Status': status,
            'Reasons': reasons
        }

        # print(json.dumps(result, indent=4))
        return result


def create_campaign():
    """
    Membuat campaign baru dalam database dan mengembalikan ID campaign yang dibuat.
    """
    try:
        connection = connect_to_database()
        if connection is None:
            logger.error("Gagal menghubungkan ke database saat membuat campaign.")
            return None

        cursor = connection.cursor()
        
        sql = "INSERT INTO campaign (timestamp) VALUES (DATETIME('now'))"
        cursor.execute(sql)
        campaign_id = cursor.lastrowid

        connection.commit()
        logger.info(f"Campaign baru dibuat dengan ID={campaign_id}")

        return campaign_id
    except Exception as e:
        logger.exception(f"Error saat membuat campaign: {e}")
        return None
    finally:
        if connection:
            cursor.close()
            connection.close()
            logger.debug("Koneksi database ditutup setelah pembuatan campaign.")

def save_gsm_data_to_db(gsm_data, campaign_id):
    try:
        connection = connect_to_database()
        if connection is None:
            logger.error(f"Gagal menghubungkan ke database saat menyimpan data GSM untuk Campaign ID={campaign_id}")
            return

        cursor = connection.cursor()
        logger.info(f"Mulai menyimpan data GSM untuk Campaign ID={campaign_id}, total data: {len(gsm_data)}")

        for data in gsm_data:
            mcc, mnc, local_area_code, cell_identity, arfcn = (
                data.get('MCC'),
                data.get('MNC'),
                data.get('Local Area Code'),
                data.get('Cell Identity'),
                data.get('ARFCN'),
            )

            # Kasus 1: Data memiliki MCC, MNC, Local Area Code, dan Cell Identity
            if all([mcc, mnc, local_area_code, cell_identity]):
                check_sql = """
                SELECT id FROM gsm 
                WHERE mcc = ? AND mnc = ? AND local_area_code = ? AND cell_identity = ? AND id_campaign = ?
                """
                cursor.execute(check_sql, (mcc, mnc, local_area_code, cell_identity, campaign_id))
                results = cursor.fetchall()

                if not results:
                    sql = """
                    INSERT INTO gsm (mcc, mnc, operator, local_area_code, arfcn, cell_identity, rxlev, rxlev_access_min, status, id_campaign)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    values = (
                        data.get('MCC'),
                        data.get('MNC'),
                        data.get('operator'),
                        data.get('Local Area Code'),
                        data.get('ARFCN'),
                        data.get('Cell Identity'),
                        data.get('RxLev'),
                        data.get('RXLEV-ACCESS-MIN'),
                        data.get('Status'),
                        campaign_id
                    )
                    cursor.execute(sql, values)
                    schedule_update_broadcast(campaign_id)

            #  Kasus 2: MCC dan MNC kosong, tetapi Status memiliki nilai
            elif (not mcc or not mnc) and data.get('Status') is not None:
                select_sql = """
                SELECT id FROM gsm WHERE arfcn = ? AND id_campaign = ?
                """
                cursor.execute(select_sql, (data.get('ARFCN'), campaign_id))
                results = cursor.fetchall()

                if results:
                    update_sql = """
                    UPDATE gsm SET status = ? WHERE arfcn = ? AND id_campaign = ?
                    """
                    cursor.execute(update_sql, (data.get('Status'), data.get('ARFCN'), campaign_id))
                    logger.info(f"Status GSM diperbarui untuk Campaign ID={campaign_id}, ARFCN={data.get('ARFCN')}")

                    schedule_update_broadcast(campaign_id)

        connection.commit()
        logger.info(f"Data GSM berhasil disimpan untuk Campaign ID={campaign_id}")

    except Exception as e:
        logger.exception(f"Error saat menyimpan data GSM ke database untuk Campaign ID={campaign_id}: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()
            logger.debug(f"Koneksi database ditutup setelah menyimpan data GSM untuk Campaign ID={campaign_id}")

# Fungsi untuk menyimpan data LTE ke database
def save_lte_data_to_db(lte_data, campaign_id):
    """
    Menyimpan data LTE yang telah diparsing ke dalam database.
    """
    try:
        connection = connect_to_database()
        if connection is None:
            logger.error(f"Gagal menghubungkan ke database saat menyimpan data LTE untuk Campaign ID={campaign_id}")
            return

        cursor = connection.cursor()
        logger.info(f"Mulai menyimpan data LTE untuk Campaign ID={campaign_id}, total data: {len(lte_data)}")

        for data in lte_data:
            mcc, mnc, tracking_area_code, cell_identity, arfcn = (
                data.get('MCC'),
                data.get('MNC'),
                data.get('Tracking Area Code'),
                data.get('Cell Identity'),
                data.get('ARFCN'),
            )

            # Kasus 1: Data memiliki MCC, MNC, TAC, dan Cell Identity
            if all([mcc, mnc, tracking_area_code, cell_identity]):
                check_sql = """
                SELECT id FROM lte 
                WHERE mcc = ? AND mnc = ? AND tracking_area_code = ? AND cell_identity = ? AND id_campaign = ?
                """
                cursor.execute(check_sql, (mcc, mnc, tracking_area_code, cell_identity, campaign_id))
                results = cursor.fetchall()

                if not results:
                    sql = """
                    INSERT INTO lte (mcc, mnc, operator, arfcn, cell_identity, tracking_area_code, frequency_band_indicator, 
                                     signal_level, snr, rx_lev_min, status, id_campaign)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    values = (
                        mcc,
                        mnc,
                        data.get('operator'),
                        arfcn,
                        cell_identity,
                        tracking_area_code,
                        data.get('Frequency Band Indicator'),
                        data.get('signal_level'),
                        data.get('snr'),
                        data.get('Rx Level Min'),
                        data.get('Status'),
                        campaign_id
                    )
                    cursor.execute(sql, values)
                    schedule_update_broadcast(campaign_id)

            # Kasus 2: MCC dan MNC kosong, tetapi Status memiliki nilai
            elif (not mcc or not mnc) and data.get('Status') is not None:
                select_sql = """
                SELECT id FROM lte WHERE arfcn = ? AND id_campaign = ?
                """
                cursor.execute(select_sql, (arfcn, campaign_id))
                results = cursor.fetchall()

                if results:
                    update_sql = """
                    UPDATE lte SET status = ? WHERE arfcn = ? AND id_campaign = ?
                    """
                    cursor.execute(update_sql, (data.get('Status'), arfcn, campaign_id))
                    logger.info(f"Status LTE diperbarui untuk Campaign ID={campaign_id}, ARFCN={arfcn}")

                    schedule_update_broadcast(campaign_id)

        connection.commit()
        logger.info(f"Data LTE berhasil disimpan untuk Campaign ID={campaign_id}")

    except Exception as e:
        logger.exception(f"Error saat menyimpan data LTE ke database untuk Campaign ID={campaign_id}: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()
            logger.debug(f"Koneksi database ditutup setelah menyimpan data LTE untuk Campaign ID={campaign_id}")

global_cap = None

def start_live_capture(stop_event, campaign_id):
    global global_cap

    output_file_gsm = 'gsm_data.json'
    output_file_lte = 'lte_data.json'
    
    existing_data_gsm = []
    existing_data_lte = []
    packet_count = 0
    start_time = time.time()
    
    interface = 'lo' 

    try:
        cap = pyshark.LiveCapture(interface=interface)
        global_cap = cap 
        logger.info(f"Memulai live capture di interface '{interface}' untuk Campaign ID={campaign_id}")
    except Exception as e:
        logger.error(f"Error initializing live capture on interface '{interface}': {e}")
        return
    
    try:
        cap.set_debug()
        for packet in cap.sniff_continuously():
            if stop_event.is_set():  
                logger.info("Stop signal diterima, menghentikan live capture...")
                break 

            full_packet_structure = str(packet)
            cleaned_structure = remove_ansi_escape_codes(full_packet_structure)
            cleaned_structure = clean_packet_structure(cleaned_structure)

            # Parsing tipe paket
            payload_type_matches = re.findall(r'Payload Type:\s*(\w+)', cleaned_structure)
            protocol_type_matches = re.findall(r'Protocol:\s*(\w+)', cleaned_structure)
            arfcn_type_matches = re.findall(r'ARFCN:\s*(\d+)', cleaned_structure)
            print(payload_type_matches)
            if payload_type_matches:
                payload_type = payload_type_matches[0]
                protocol_type = protocol_type_matches[0] if protocol_type_matches else None
                arfcn_type = arfcn_type_matches[0] if arfcn_type_matches else None
                print('protocol type',protocol_type)
                if protocol_type == 'UDP':
                    if payload_type == 'GSM':
                        gsm_data = evaluate_packet_gsm(cleaned_structure)
                        if gsm_data:
                            logger.debug(f"Data GSM ditemukan: {gsm_data}")
                            existing_data_gsm.append(gsm_data)
                    elif payload_type == 'LTE' and arfcn_type != '0':
                        lte_data = evaluate_packet_lte(cleaned_structure)
                        if lte_data:
                            logger.debug(f"Data LTE ditemukan: {lte_data}")
                            existing_data_lte.append(lte_data)
            packet_count += 1

            if packet_count % 10 == 0 or (time.time() - start_time) >= 60:
                with open(output_file_gsm, 'w') as f:
                    json.dump(existing_data_gsm, f, indent=4)
                with open(output_file_lte, 'w') as f:
                    json.dump(existing_data_lte, f, indent=4)
                
                save_gsm_data_to_db(existing_data_gsm, campaign_id)
                save_lte_data_to_db(existing_data_lte, campaign_id)
                
                logger.info(f"Data GSM dan LTE disimpan ke database setelah {packet_count} paket.")
                start_time = time.time()
                existing_data_gsm = []
                existing_data_lte = []

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



