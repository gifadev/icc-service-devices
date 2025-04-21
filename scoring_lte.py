import pyshark
import argparse
import logging
import re

logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s - %(levelname)s - %(message)s")


def find_field_value(text, field_name):
    pattern = re.compile(rf"{field_name}\s*:\s*([^\n]+)")
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return None


def parse_plmn_identities_global(text):
    m = re.search(r"plmn-IdentityList:\s*(\d+)\s*items", text, re.IGNORECASE)
    if m:
        plmn_count = int(m.group(1))
    else:
        plmn_count = 1

    m_mcc = re.search(r"mcc:\s*(\d+)\s*items", text, re.IGNORECASE)
    if not m_mcc:
        return None
    expected_mcc = int(m_mcc.group(1))

    m_mnc = re.search(r"mnc:\s*(\d+)\s*items", text, re.IGNORECASE)
    if not m_mnc:
        return None
    expected_mnc = int(m_mnc.group(1))

    total_expected = plmn_count * (expected_mcc + expected_mnc)

    digits = re.findall(r"MCC-MNC-Digit:\s*([^\n]+)", text)
    if len(digits) < total_expected:
        logging.error("Jumlah digit MCC tidak mencukupi. Ditemukan %d, diharapkan %d", len(digits), total_expected)
        return None

    identities = []
    for i in range(plmn_count):
        start = i * (expected_mcc + expected_mnc)
        block = digits[start: start + (expected_mcc + expected_mnc)]
        identities.append({
            'mcc': block[:expected_mcc],
            'mnc': block[expected_mcc: expected_mcc+expected_mnc]
        })

    return identities, expected_mcc, expected_mnc, plmn_count


def extract_unique_key(rrc_text):
    """
    Membentuk key unik berdasarkan kombinasi parameter.
    Utama: cellIdentity dan trackingAreaCode.
    Jika kedua field tersebut tidak tersedia, fallback ke kombinasi:
      PLMN Identity (MCC & MNC) dan q-RxLevMin.
    """
    cell_id = find_field_value(rrc_text, "cellIdentity")
    tac = find_field_value(rrc_text, "trackingAreaCode")
    if cell_id and tac:
        return f"{cell_id.strip()}-{tac.strip()}"
    
    # Fallback: gunakan PLMN dan q-RxLevMin
    q_rx = find_field_value(rrc_text, "q-RxLevMin")
    plmn_result = parse_plmn_identities_global(rrc_text)
    if plmn_result:
        identities, expected_mcc, expected_mnc, plmn_count = plmn_result
        # Gunakan identity pertama sebagai representasi
        identity = identities[0]
        mcc_str = "".join(identity['mcc'])
        mnc_str = "".join(identity['mnc'])
        return f"{mcc_str}{mnc_str}-{q_rx}"
    return None


def detect_fake_bts(rrc_text):
    """
    Analisis pesan RRC untuk mendeteksi indikasi fake BTS berdasarkan parameter-parameter:
      - Multiple PLMN Identity entries
      - Perubahan System Info Value Tag
      - Irregular SIB Mapping count (0 atau 3 items)
      - Suspicious q-RxLevMin value (misalnya -140dBm)
      - Kehadiran field p-Max
      - Adanya nonCriticalExtension
    Mengembalikan skor dan daftar alasan (indikator) yang ditemukan.
    """
    score = 0
    reasons = []
    
    if "plmn-IdentityList: 2 items" in rrc_text:
        score += 1
        reasons.append("Multiple PLMN Identity entries")
    
    if "SI Info Value changed" in rrc_text:
        score += 1
        reasons.append("System Info Value Tag change warning")
    
    if "sib-MappingInfo: 0 items" in rrc_text or "sib-MappingInfo: 3 items" in rrc_text:
        score += 1
        reasons.append("Irregular SIB Mapping count")
    
    if "q-RxLevMin: -140dBm" in rrc_text:
        score += 1
        reasons.append("Suspicious q-RxLevMin value")
    
    if "p-Max" in rrc_text:
        score += 1
        reasons.append("Presence of p-Max field")
    
    if "nonCriticalExtension" in rrc_text:
        score += 1
        reasons.append("Existence of nonCriticalExtension field")
        
    return score, reasons


def explore_lte_rrc(pkt, seen_keys):
    try:
        print("Packet Number:", pkt.number)
    except AttributeError:
        print("Packet (no number attribute)")

    # Pengambilan nilai ARFCN dari layer GSMTAP (jika ada)
    if 'GSMTAP' in pkt:
        gsm_layer = pkt['GSMTAP']
        gsm_txt = str(gsm_layer)
        print(gsm_layer)
        print(dir(gsm_layer))
        clean_txt = re.sub(r'\x1b\[[0-9;]*m', '', gsm_txt)
        pattern = r"=\s*ARFCN:\s*([0-9]+)"
        m = re.search(pattern, clean_txt)
        if m:
            print("ARFCN:", m.group(1))
        else:
            print("ARFCN tidak ditemukan.")

    if 'LTE_RRC' in pkt:
        rrc_layer = pkt['LTE_RRC']
        rrc_text = str(rrc_layer)
        print(rrc_layer)
        
        # Filter duplicate: buat key unik dari paket
        unique_key = extract_unique_key(rrc_text)
        if unique_key:
            if unique_key in seen_keys:
                logging.debug("Paket dengan key %s sudah diproses, skip.", unique_key)
                return  # Skip paket duplicate
            else:
                seen_keys.add(unique_key)
        else:
            logging.warning("Tidak dapat membuat key unik dari paket, proses paket tetap dilakukan.")

        # Ekstraksi field q-RxLevMin
        q_rx_lev_min = find_field_value(rrc_text, "q-RxLevMin")
        if q_rx_lev_min:
            print("\nq-RxLevMin:", q_rx_lev_min)
        else:
            print("\nField q-RxLevMin tidak ditemukan dengan regex.")

        # Parsing PLMN Identity
        result = parse_plmn_identities_global(rrc_text)
        if result:
            identities, expected_mcc, expected_mnc, plmn_count = result
            for idx, identity in enumerate(identities):
                print(f"\nParsed PLMN Identity {idx+1}:")
                print(f"  Expected MCC Digits: {expected_mcc}")
                print(f"  Expected MNC Digits: {expected_mnc}")
                print("  MCC:", identity['mcc'])
                print("  MNC:", identity['mnc'])
        else:
            print("\nInformasi PLMN identity (MCC/MNC) tidak ditemukan atau format tidak sesuai.")

        # Deteksi fake BTS berdasarkan indikator yang telah ditentukan
        score, reasons = detect_fake_bts(rrc_text)
        threshold = 3
        is_fake = score >= threshold

        print("\n==== Deteksi Fake BTS ====")
        print(f"Skor kecurigaan: {score} (Threshold: {threshold})")
        print("Hasil deteksi: Fake BTS" if is_fake else "Hasil deteksi: BTS Asli")
        if reasons:
            print("Indikator yang ditemukan:")
            for reason in reasons:
                print(" -", reason)
        else:
            print("Tidak ada indikasi tambahan yang terdeteksi.")
    else:
        print("Layer LTE_RRC tidak ditemukan pada paket ini.")

    print("======================================\n")


def main():
    parser = argparse.ArgumentParser(
        description="Eksplorasi LTE_RRC dari file PCAP untuk mengekstrak q-RxLevMin, MCC, MNC, dan mendeteksi fake BTS menggunakan regex."
    )
    parser.add_argument("--pcap", help="Path ke file PCAP (misalnya: lte_capture.pcapng)")
    parser.add_argument("--live", action="store_true", help="Aktifkan live capture (dengan parameter --interface)")
    parser.add_argument("--interface", help="Interface (misalnya: eth0) jika live capture")
    args = parser.parse_args()

    if args.live:
        if not args.interface:
            parser.error("--interface dibutuhkan untuk live capture")
        logging.info("Memulai live capture pada interface %s...", args.interface)
        capture = pyshark.LiveCapture(interface=args.interface, display_filter='lte_rrc')
    else:
        if not args.pcap:
            parser.error("Harap sertakan --pcap atau --live")
        logging.info("Memulai parsing file PCAP: %s", args.pcap)
        capture = pyshark.FileCapture(args.pcap, display_filter='lte-rrc.plmn_IdentityList')
    
    # Set untuk menyimpan key unik paket untuk menghindari duplikasi
    seen_keys = set()

    try:
        for pkt in capture:
            if 'LTE_RRC' in pkt:
                print("\n==== Eksplorasi Paket {} ====".format(getattr(pkt, 'number', 'Unknown')))
                explore_lte_rrc(pkt, seen_keys)
    except KeyboardInterrupt:
        logging.info("Eksplorasi dihentikan oleh pengguna.")
    except Exception as e:
        logging.error("Terjadi kesalahan selama eksplorasi: %s", e)
    finally:
        capture.close()


if __name__ == "__main__":
    main()
