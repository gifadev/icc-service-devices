import pyshark
import re
import json
import time
from database_config import connect_to_database
import pyshark.tshark.tshark
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
    print("ini rxlev_access_min_matches",rxlev_access_min_matches)
    if rxlev_access_min_matches:
        range_str = rxlev_access_min_matches.group(1)
        # Ekstrak kedua angka dari string
        bounds = re.findall(r'-?\d+', range_str)
        if len(bounds) == 2:
            lower = int(bounds[0])
            upper = int(bounds[1])
            print("ini lower",lower)
            print("ini upper", upper)
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
    # data['Status'] = True
    security_header_type_patteren = r'Security header type:\s*(\w+)'
    security_header_type_matches = re.search(security_header_type_patteren, cleaned_structure)
    print("#############in security_header_type_matches type#############", security_header_type_matches)
    if security_header_type_matches:
        # print(security_header_type_matches[0])
        if security_header_type_matches  == 'Plain':
            print("***********in security_header_type_matches type***********", security_header_type_matches)
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
    # data['Status'] = True
    security_header_type_patteren = r'Security header type:\s*(\w+)'
    security_header_type_matches = re.search(security_header_type_patteren, cleaned_structure)
    print("#############in security_header_type_matches type#############", security_header_type_matches)
    if security_header_type_matches:
        security_header_type = security_header_type_matches.group(1)
        if security_header_type == 'Plain':
            print("***********in security_header_type_matches type***********", security_header_type_matches)
            data['Status'] = False  
            
    return data

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

            # 🔹 Kasus 1: Data memiliki MCC, MNC, Local Area Code, dan Cell Identity
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

            # 🔹 Kasus 2: MCC dan MNC kosong, tetapi Status memiliki nilai
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

            # 🔹 Kasus 1: Data memiliki MCC, MNC, TAC, dan Cell Identity
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

            # 🔹 Kasus 2: MCC dan MNC kosong, tetapi Status memiliki nilai
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
    
    interface = 'lo'  # Sesuaikan dengan antarmuka jaringan yang digunakan

    try:
        cap = pyshark.LiveCapture(interface=interface)
        global_cap = cap  # simpan secara global agar bisa diakses dari endpoint stop
        logger.info(f"Memulai live capture di interface '{interface}' untuk Campaign ID={campaign_id}")
    except Exception as e:
        logger.error(f"Error initializing live capture on interface '{interface}': {e}")
        return
    
    try:
        cap.set_debug()
        for packet in cap.sniff_continuously():
            # Jika stop_event sudah diset, langsung keluar dari loop
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

            if payload_type_matches:
                payload_type = payload_type_matches[0]
                protocol_type = protocol_type_matches[0] if protocol_type_matches else None
                arfcn_type = arfcn_type_matches[0] if arfcn_type_matches else None

                if protocol_type == 'UDP':
                    if payload_type == 'GSM':
                        gsm_data = extract_gsm_data(cleaned_structure)
                        if gsm_data:
                            logger.debug(f"Data GSM ditemukan: {gsm_data}")
                            existing_data_gsm.append(gsm_data)
                    elif payload_type == 'LTE' and arfcn_type != '0':
                        lte_data = extract_lte_data(cleaned_structure)
                        if lte_data:
                            logger.debug(f"Data LTE ditemukan: {lte_data}")
                            existing_data_lte.append(lte_data)
            packet_count += 1

            # Simpan data setiap 10 paket atau setiap 60 detik
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