import pyshark
import argparse
import logging
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def convert_hex_to_dec(value: Any) -> Any:
    """
    Converts a hexadecimal string (if applicable) to an integer.
    If the value starts with "0x", it is assumed to be in hexadecimal format.
    
    Args:
        value (Any): The value to convert. It may be a string representing a hex value.
    
    Returns:
        Any: The integer conversion if possible, otherwise returns the original value.
    """
    if isinstance(value, str) and value.lower().startswith("0x"):
        try:
            return int(value, 16)
        except ValueError:
            return value
    return value


def get_radio_type(arfcn: Any) -> str:
    """
    Determines the radio type (GSM, UMTS, or LTE) based on the provided ARFCN (Absolute Radio Frequency Channel Number).
    
    Args:
        arfcn (Any): The ARFCN value. It may be a string or a numeric type.
    
    Returns:
        str: "GSM", "UMTS", "LTE", or "Unknown" if it cannot be determined.
    """
    try:
        arfcn_int = int(arfcn)
    except (ValueError, TypeError):
        return "Unknown"

    # Conditions based on ARFCN ranges for GSM, UMTS, and LTE
    if (1 <= arfcn_int <= 124) or (128 <= arfcn_int <= 251) or (512 <= arfcn_int <= 885):
        return "GSM"
    if 9662 <= arfcn_int <= 10838:
        return "UMTS"
    return "LTE"


def score_cro(cro: Any) -> float:
    """
    Calculates the score for the CRO (Cell Reselect Offset). This value influences
    cell reselection decisions by indicating preference levels. Lower score means a
    lesser offset; a higher score suggests a greater offset.
    
    Calculation Explanation:
    - If cro is 0 or an error occurs, a default high score (40) is returned.
    - For cro <= 115, score is 0, meaning minimal offset.
    - For cro >= 130, maximum score of 40 is assigned.
    - For values between 115 and 130, the score is proportionally interpolated.
    
    Args:
        cro (Any): The CRO value.
    
    Returns:
        float: The calculated score.
    """
    try:
        cro_val = float(cro)
    except (ValueError, TypeError):
        return 40.0
    if cro_val == 0:
        return 40.0
    if cro_val <= 115:
        return 0.0
    elif cro_val >= 130:
        return 40.0
    else:
        return ((cro_val - 115) / 15) * 40


def score_rxlevmin(rxlev: Any) -> float:
    """
    Calculates the score for RXLEV Access Minimum (the minimum received signal level 
    required for access). The score represents how much the measured value deviates 
    from an acceptable threshold.
    
    Calculation Explanation:
    - If rxlev is 0 or cannot be parsed, a default score of 40 is returned.
    - For values greater than -105, score is 0 (i.e., signal is strong enough).
    - For values less than or equal to -110, maximum score of 40 is returned.
    - For values between -105 and -110, the score is proportionally interpolated.
    
    Args:
        rxlev (Any): The raw RXLEV value.
    
    Returns:
        float: The calculated score.
    """
    try:
        rxlev_val = float(rxlev)
    except (ValueError, TypeError):
        return 40.0
    if rxlev_val == 0:
        return 40.0
    if rxlev_val > -105:
        return 0.0
    elif rxlev_val <= -110:
        return 40.0
    else:
        return ((-105 - rxlev_val) / 5) * 40


def score_c2_indicator(si2quater: Any) -> float:
    """
    Calculates the score for the C2 indicator. The C2 indicator typically flags certain
    conditions in GSM networks:
      - If the indicator is "true", "yes", or "1", then the score is 0 (no penalty).
      - Otherwise, a penalty score of 20 is assigned.
      
    This metric is used as an additional parameter in risk evaluation.
    
    Args:
        si2quater (Any): The C2 indicator value.
    
    Returns:
        float: The calculated score.
    """
    if str(si2quater).lower() in ["true", "yes", "1"]:
        return 0.0
    else:
        return 20.0


def score_t3212(t3212: Any) -> float:
    """
    Calculates the score based on the T3212 timer value which indicates the timeout
    for periodic location updating. In many systems, a lower timer (closer to 0) could
    imply a higher risk (thus higher score) in the context of fraudulent behavior.
    
    Calculation Explanation:
    - If t3212 is 0 or cannot be parsed, a default score of 20 is returned.
    - For values less than 30, the score is proportional to how much the timer is below 30.
    - For values 30 or above, no penalty is applied (score 0).
    
    Args:
        t3212 (Any): The raw T3212 timer value.
    
    Returns:
        float: The calculated score.
    """
    try:
        t3212_val = float(t3212)
    except (ValueError, TypeError):
        return 20.0
    if t3212_val <= 0:
        return 20.0
    if t3212_val < 30:
        return ((30 - t3212_val) / 30) * 20
    else:
        return 0.0


def score_c1(rxlev: Any, rxlev_access_min: Any, hysteresis: float = 0) -> float:
    """
    Calculates the value for C1. C1 is a metric that represents the difference between the
    received signal level (rxlev) and the minimum access level (rxlev_access_min). It may also
    include a hysteresis factor to avoid rapid toggling between cells.
    
    A higher C1 value generally indicates that the signal is well above the minimum threshold.
    A lower or negative C1 might flag potential issues.
    
    Args:
        rxlev (Any): The current received signal level.
        rxlev_access_min (Any): The minimum required access signal level.
        hysteresis (float, optional): A value to be subtracted to account for system hysteresis.
    
    Returns:
        float: The calculated C1 value.
    """
    try:
        rxlev_val = float(rxlev)
        rxmin_val = float(rxlev_access_min)
    except (ValueError, TypeError):
        return 999.0  # Flag invalid computation with a high error value
    return (rxlev_val - rxmin_val) - hysteresis


def score_c2(cro: Any, penalty_time: Any, temp_offset: Any = 0) -> float:
    """
    Calculates the value for C2. C2 is a metric that combines the cell reselection offset (CRO)
    with additional parameters like penalty time and temporary offset. The idea is to adjust the
    CRO value by considering network-imposed penalties and temporary factors.
    
    Calculation Explanation:
    - If the values cannot be parsed, returns a high error value (999).
    - Otherwise, it subtracts the sum of penalty time and temporary offset from the CRO value.
    
    Args:
        cro (Any): The cell reselection offset value.
        penalty_time (Any): Penalty time associated with the cell reselection.
        temp_offset (Any, optional): A temporary offset value.
    
    Returns:
        float: The calculated C2 value.
    """
    try:
        cro_val = float(cro)
        # Convert temporary offset and penalty time to float values
        pt_val = float(penalty_time)
    except (ValueError, TypeError):
        return 999.0
    return cro_val - (float(temp_offset) + pt_val)


def parse_gsm_ccch(pkt: pyshark.packet.packet.Packet) -> Optional[Dict[str, Any]]:
    """
    Parses the GSM_A.CCCH layer from the packet to extract key cell identification data and
    parameters necessary for risk scoring. These include:
      - ci (Cell Identity)
      - mcc (Mobile Country Code)
      - mnc (Mobile Network Code)
      - lac (Location Area Code)
    Along with this, it retrieves the raw values for scoring calculations, for example:
      - raw CRO (gsm_a.rr.cell_reselect_offset)
      - raw RXLEV (gsm_a.rr.rxlev_access_min)
      - raw C2 Indicator (gsm_a.rr.si2quater_indicator)
      - raw T3212 (gsm_a.si3.t3212)
    
    The raw values are temporarily stored (with a preceding underscore) for use in overall risk calculations.
    
    Args:
        pkt (pyshark.packet.packet.Packet): The packet object received from PyShark.
    
    Returns:
        Optional[Dict[str, Any]]: A dictionary of the parsed data or None if an error occurs.
    """
    try:
        gsm_ccch = pkt["GSM_A.CCCH"]

        # Retrieve basic cell parameters and convert from hexadecimal if needed
        ci_value = convert_hex_to_dec(getattr(gsm_ccch, "gsm_a_bssmap_cell_ci", None))
        mcc_value = convert_hex_to_dec(getattr(gsm_ccch, "e212_lai_mcc", None))
        mnc_value = convert_hex_to_dec(getattr(gsm_ccch, "e212_lai_mnc", None))
        lac_value = convert_hex_to_dec(getattr(gsm_ccch, "gsm_a_lac", None))

        data = {"ci": ci_value, "mcc": mcc_value, "mnc": mnc_value, "lac": lac_value}

        # Retrieve raw parameters for scoring calculations
        raw_cro   = getattr(gsm_ccch, "gsm_a.rr.cell_ _offset", None)
        raw_rxlev = getattr(gsm_ccch, "gsm_a.rr.rxlev_access_min", None)
        raw_si2   = getattr(gsm_ccch, "gsm_a.rr.si2quater_indicator", None)
        raw_t3212 = getattr(gsm_ccch, "gsm_a.si3.t3212", None)
        print(raw_cro,raw_rxlev,raw_si2,raw_t3212)

        # Additional parameters that modify the C2 score
        raw_penalty = getattr(gsm_ccch, "gsm_a.si3.penalty_time", None)
        raw_tmp_off = getattr(gsm_ccch, "gsm_a.si3.temporary_offset", None)

        # Calculate individual scores based on the raw values
        data["cro_score"] = round(score_cro(raw_cro), 2)
        data["rxlevmin_score"] = round(score_rxlevmin(raw_rxlev), 2)
        data["c2_indicator"] = round(score_c2_indicator(raw_si2), 2)
        data["t3212_score"] = round(score_t3212(raw_t3212), 2)

        # Calculate C1: differences between the received signal level and minimum access level.
        # Here, -100 and -110 are sample values; in practice, they would be derived from the packet.
        data["C1"] = round(score_c1(-100, -110, hysteresis=0), 2)

        # Calculate C2: Adjusts the cell reselection offset (CRO) by subtracting the penalty and temporary offset.
        # A higher C2 score could indicate less favorable conditions.
        data["C2"] = round(score_c2(raw_cro or 0, raw_penalty or 0, raw_tmp_off or 0), 2)

        # Calculate RSSI from the RXLEV if possible. RSSI (Received Signal Strength Indicator) is computed
        # by adding the raw RXLEV value to a base (-110). A better signal yields a higher RSSI.
        if raw_rxlev is not None:
            try:
                rxlev_val = float(raw_rxlev)
                data["rssi"] = -110 + rxlev_val
            except Exception:
                data["rssi"] = None
        else:
            data["rssi"] = None

        # Preserve raw values for calculating overall risk score later
        data["_raw_cro"] = raw_cro
        data["_raw_rxlev"] = raw_rxlev
        data["_raw_si2"] = raw_si2
        data["_raw_t3212"] = raw_t3212

        return data

    except Exception as e:
        logging.error("Error parsing GSM_A.CCCH: %s", e)
        return None


def parse_gsm_tap(pkt: pyshark.packet.packet.Packet, parsed_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parses the GSMTAP layer to append radio-specific information to the parsed data.
    
    In this layer, we extract:
      - ARFCN (which is used to determine the radio type).
      - RSSI, if present (this can override the previous RSSI value if available).
    
    Args:
        pkt (pyshark.packet.packet.Packet): The packet object.
        parsed_data (Dict[str, Any]): The dictionary of data parsed from the GSM_A.CCCH layer.
    
    Returns:
        Optional[Dict[str, Any]]: The updated dictionary with GSMTAP info, or None if parsing fails.
    """
    try:
        gsm_tap = pkt["GSMTAP"]
        arfcn_val = getattr(gsm_tap, "arfcn", None)

        # Filter out packets with invalid ARFCN (None or "0")
        if arfcn_val is None or str(arfcn_val) == "0":
            return None

        parsed_data["arfcn"] = arfcn_val
        parsed_data["radio_type"] = get_radio_type(arfcn_val)

        raw_rssi = getattr(gsm_tap, "rssi", None)
        if raw_rssi is not None:
            parsed_data["rssi"] = raw_rssi

        return parsed_data

    except Exception as e:
        logging.error("Error parsing GSMTAP: %s", e)
        return None


def parse_packet(pkt: pyshark.packet.packet.Packet) -> Optional[Dict[str, Any]]:
    """
    Parses an entire packet to extract cell and radio data and calculates a composite risk score.
    
    Calculation Details:
      - Uses individual functions to score parameters:
          * CRO score: Reflects the cell reselection offset condition.
          * RXLEV score: Indicates the received signal strength relative to a minimum threshold.
          * C2 Indicator score: Applies a penalty based on specific network indicators.
          * T3212 score: Considers the timer indicating periodic location update timeout.
      - The overall risk is calculated as the sum of these scores.
      - A threshold of 60 is used to determine whether the BTS (Base Transceiver Station) is considered "fake" or "dangerous".
      - Additionally, C1 and C2 values are computed:
          * C1 represents the margin between received signal and the minimum access level.
          * C2 adjusts the cell reselection offset (CRO) based on penalty parameters.
    
    Args:
        pkt (pyshark.packet.packet.Packet): The packet to be parsed.
    
    Returns:
        Optional[Dict[str, Any]]: The parsed packet data with computed scores, or None if parsing fails.
    """
    parsed_data = parse_gsm_ccch(pkt)
    if parsed_data is None:
        return None

    parsed_data = parse_gsm_tap(pkt, parsed_data)
    if parsed_data is None:
        return None

    # Calculate the overall risk score by summing individual scoring values.
    # This composite risk score is used to flag potential anomalies or fake BTS.
    total_risk = (
        score_cro(parsed_data.get("_raw_cro"))
        + score_rxlevmin(parsed_data.get("_raw_rxlev"))
        + score_c2_indicator(parsed_data.get("_raw_si2"))
        + score_t3212(parsed_data.get("_raw_t3212"))
    )
    parsed_data["total_risk"] = round(total_risk, 2)

    # Advanced detection logic: If the CRO score is less than 40 
    # but the total risk score exceeds the threshold, mark the BTS as fake.
    THRESHOLD = 60
    parsed_data["is_fake"] = (parsed_data.get("cro_score", 0) < 40) and (total_risk > THRESHOLD)

    # Remove the raw parameters from the output as they are not needed for final reporting
    for key in ["_raw_cro", "_raw_rxlev", "_raw_si2", "_raw_t3212"]:
        parsed_data.pop(key, None)
    return parsed_data


def main():
    parser = argparse.ArgumentParser(
        description="Process GSM PCAP file or live capture for fake BTS detection."
    )
    parser.add_argument("--pcap", help="Path to the PCAP file (e.g., gsm.pcapng)")
    parser.add_argument("--live", action="store_true", help="Enable live capture mode")
    parser.add_argument("--interface", help="Network interface for live capture (e.g., lo0)")
    args = parser.parse_args()

    capture = None

    if args.live:
        # When live capture mode is selected, ensure that an interface is provided.
        if not args.interface:
            parser.error("--interface is required when --live is enabled")
        logging.info("Starting live capture on interface %s...", args.interface)
        capture = pyshark.LiveCapture(
            interface=args.interface,
            display_filter="gsm_a.rr.system_information_type_2ter",
        )
    else:
        if not args.pcap:
            parser.error("Either --pcap must be provided for file capture or --live for live capture")
        logging.info("Starting packet capture from file %s...", args.pcap)
        capture = pyshark.FileCapture(
            args.pcap, display_filter="gsm_a.rr.system_information_type_2ter"
        )

    unique_records = set()

    try:
        for pkt in capture:
            parsed = parse_packet(pkt)
            if parsed is not None:
                # Remove intermediate scores that are not intended for final output (for clarity)
                for key in ["rxlevmin_score", "c2_indicator", "t3212_score"]:
                    parsed.pop(key, None)
                # Rename keys for output clarity:
                # "cro" for cell reselection offset score, "c1" and "c2" for their respective calculated values.
                parsed["cro"] = parsed.pop("cro_score", None)
                parsed["c1"] = parsed.pop("C1", None)
                parsed["c2"] = parsed.pop("C2", None)

                # Create a record key to ensure uniqueness when printing output based on ARFCN and risk score.
                record_key = (str(parsed.get("arfcn")), str(parsed.get("total_risk")))
                if record_key not in unique_records:
                    unique_records.add(record_key)
                    # Set risk_status based on the fake detection flag: "danger" for fake BTS, "safe" otherwise.
                    parsed["risk_status"] = "danger" if parsed.get("is_fake") else "safe"
                    # Remove the total_risk key from output if it is not needed
                    parsed.pop("total_risk", None)
                    print(parsed)

    except KeyboardInterrupt:
        logging.info("Packet capture interrupted by user.")
    except Exception as e:
        logging.error("Error during packet capture processing: %s", e)
    finally:
        if capture is not None:
            capture.close()


if __name__ == "__main__":
    main()
