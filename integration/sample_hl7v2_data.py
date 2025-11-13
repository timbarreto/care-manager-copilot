#!/usr/bin/env python3
"""
Sample HL7v2 data for testing $convert-data operation.

Contains realistic HL7v2 messages for two patients:
- Patient 1: John Doe (admission + lab results)
- Patient 2: Jane Smith (admission + lab results)
"""

from datetime import datetime

# Generate current timestamp for messages
def get_timestamp():
    """Return current timestamp in HL7v2 format (YYYYMMDDHHMMSS)."""
    return datetime.now().strftime("%Y%m%d%H%M%S")

# Patient 1: John Doe - 65-year-old male with cardiac issues
PATIENT1_ADT_A01 = """MSH|^~\\&|HIS|MIAMI-HOSPITAL|FHIR|AZUREFHIR|{timestamp}||ADT^A01^ADT_A01|MSG{msg_id}001|P|2.5
EVN|A01|{timestamp}
PID|1||PAT001^^^MRN||DOE^JOHN^ALLEN||19590515|M|||123 OCEAN DRIVE^^MIAMI^FL^33139^USA||(305)555-1234|||S||ACC001|||123-45-6789||||MIAMI^FLORIDA
PV1|1|I|CARDIO^401^B^MIAMI-HOSPITAL^^^^DEPT|3|||DOC001^SMITH^JANE^A^^^MD|DOC001^SMITH^JANE^A^^^MD|CARDIO||||ADM||||V{timestamp}001|||||||||||||||||||MIAMI-HOSPITAL||||||||{timestamp}"""

PATIENT1_ORU_R01 = """MSH|^~\\&|LAB|MIAMI-LAB|FHIR|AZUREFHIR|{timestamp}||ORU^R01^ORU_R01|MSG{msg_id}002|P|2.5
PID|1||PAT001^^^MRN||DOE^JOHN^ALLEN||19590515|M
OBR|1|ORD{timestamp}001|LAB{timestamp}001|CBC^COMPLETE BLOOD COUNT^LN|||{timestamp}|{timestamp}|||||||{timestamp}|||DOC001^SMITH^JANE^A^^^MD||||||||LAB||||||{timestamp}|||F
OBX|1|NM|WBC^White Blood Count^LN||7.2|10*3/uL|4.0-11.0|N|||F|||{timestamp}||LAB
OBX|2|NM|RBC^Red Blood Count^LN||4.5|10*6/uL|4.5-5.5|N|||F|||{timestamp}||LAB
OBX|3|NM|HGB^Hemoglobin^LN||14.2|g/dL|13.5-17.5|N|||F|||{timestamp}||LAB
OBX|4|NM|HCT^Hematocrit^LN||42.1|%|38.8-50.0|N|||F|||{timestamp}||LAB
OBX|5|NM|PLT^Platelet Count^LN||245|10*3/uL|150-400|N|||F|||{timestamp}||LAB
OBX|6|NM|TROP^Troponin I^LN||0.8|ng/mL|0.0-0.04|H|||F|||{timestamp}||LAB"""

# Patient 2: Jane Smith - 72-year-old female with diabetes
PATIENT2_ADT_A01 = """MSH|^~\\&|HIS|MIAMI-HOSPITAL|FHIR|AZUREFHIR|{timestamp}||ADT^A01^ADT_A01|MSG{msg_id}003|P|2.5
EVN|A01|{timestamp}
PID|1||PAT002^^^MRN||SMITH^JANE^MARIE||19520320|F|||456 PALM AVENUE^^MIAMI^FL^33180^USA||(305)555-5678|||M||ACC002|||987-65-4321||||MIAMI^FLORIDA
PV1|1|I|ENDO^302^A^MIAMI-HOSPITAL^^^^DEPT|3|||DOC002^JOHNSON^ROBERT^M^^^MD|DOC002^JOHNSON^ROBERT^M^^^MD|ENDO||||ADM||||V{timestamp}002|||||||||||||||||||MIAMI-HOSPITAL||||||||{timestamp}"""

PATIENT2_ORU_R01 = """MSH|^~\\&|LAB|MIAMI-LAB|FHIR|AZUREFHIR|{timestamp}||ORU^R01^ORU_R01|MSG{msg_id}004|P|2.5
PID|1||PAT002^^^MRN||SMITH^JANE^MARIE||19520320|F
OBR|1|ORD{timestamp}002|LAB{timestamp}002|BMP^BASIC METABOLIC PANEL^LN|||{timestamp}|{timestamp}|||||||{timestamp}|||DOC002^JOHNSON^ROBERT^M^^^MD||||||||LAB||||||{timestamp}|||F
OBX|1|NM|GLU^Glucose^LN||156|mg/dL|70-100|H|||F|||{timestamp}||LAB
OBX|2|NM|BUN^Blood Urea Nitrogen^LN||18|mg/dL|7-20|N|||F|||{timestamp}||LAB
OBX|3|NM|CREAT^Creatinine^LN||1.1|mg/dL|0.6-1.2|N|||F|||{timestamp}||LAB
OBX|4|NM|NA^Sodium^LN||140|mmol/L|136-145|N|||F|||{timestamp}||LAB
OBX|5|NM|K^Potassium^LN||4.2|mmol/L|3.5-5.0|N|||F|||{timestamp}||LAB
OBX|6|NM|CL^Chloride^LN||102|mmol/L|98-107|N|||F|||{timestamp}||LAB
OBX|7|NM|CO2^Carbon Dioxide^LN||24|mmol/L|22-29|N|||F|||{timestamp}||LAB
OBX|8|NM|HBA1C^Hemoglobin A1c^LN||8.2|%|4.0-5.6|H|||F|||{timestamp}||LAB"""


def get_all_messages():
    """
    Return all sample HL7v2 messages with timestamps populated.

    Returns:
        list: List of tuples containing (patient_id, message_type, template, message_content)
    """
    timestamp = get_timestamp()
    msg_id = timestamp[-6:]  # Use last 6 digits for message ID

    messages = [
        ("PAT001", "ADT^A01", "ADT_A01", PATIENT1_ADT_A01.format(timestamp=timestamp, msg_id=msg_id)),
        ("PAT001", "ORU^R01", "ORU_R01", PATIENT1_ORU_R01.format(timestamp=timestamp, msg_id=msg_id)),
        ("PAT002", "ADT^A01", "ADT_A01", PATIENT2_ADT_A01.format(timestamp=timestamp, msg_id=msg_id)),
        ("PAT002", "ORU^R01", "ORU_R01", PATIENT2_ORU_R01.format(timestamp=timestamp, msg_id=msg_id)),
    ]

    return messages


def get_patient_messages(patient_id):
    """
    Get all messages for a specific patient.

    Args:
        patient_id: Patient identifier (e.g., "PAT001" or "PAT002")

    Returns:
        list: List of messages for the specified patient
    """
    all_messages = get_all_messages()
    return [msg for msg in all_messages if msg[0] == patient_id]


if __name__ == "__main__":
    # Display sample data
    print("=" * 80)
    print("Sample HL7v2 Messages for $convert-data Testing")
    print("=" * 80)

    messages = get_all_messages()
    for patient_id, msg_type, template, content in messages:
        print(f"\nPatient: {patient_id}")
        print(f"Message Type: {msg_type}")
        print(f"Template: {template}")
        print(f"Length: {len(content)} characters")
        print("-" * 80)
        print(content)
        print("-" * 80)
