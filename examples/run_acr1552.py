"""
Script de test para ACR1552 (funciones de alto nivel).
Usa el scanner del SDK para detectar el lector y las funciones bridge de SenseidAcr1552.
"""

import logging
from time import sleep

from senseid.readers import SupportedSenseidReader, create_SenseidReader
from senseid.readers.scanner import SenseidReaderScanner
from senseid.parsers.nfc import SenseidNfcTag

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bytes_to_hex(data):
    if data is None:
        return "None"
    return " ".join(f"{b:02X}" for b in data)


# ---------------------------------------------------------------------------
# Test blocks
# ---------------------------------------------------------------------------

def test_turn_on_field(reader):
    print("\n--- turn_on_field() ---")
    ok = reader.turn_on_field()
    print(f"  Result: {'OK' if ok else 'FAIL'}")
    return ok


def test_turn_off_field(reader):
    print("\n--- turn_off_field() ---")
    ok = reader.turn_off_field()
    print(f"  Result: {'OK' if ok else 'FAIL'}")
    return ok


def test_get_uid(reader):
    print("\n--- get_uid() ---")
    uid = reader.get_uid()
    if uid:
        print(f"  UID: {bytes_to_hex(uid)}")
    else:
        print("  No tag detected (UID = None)")
    return uid


def test_read_data(reader, start_block, n_blocks):
    print(f"\n--- read_data(start={start_block}, blocks={n_blocks}) ---")
    data = reader.read_data(start_block, n_blocks)
    if data:
        print(f"  Raw ({len(data)} bytes): {bytes_to_hex(data)}")
    else:
        print("  No data (None)")
    return data


def test_read_ndef(reader):
    print("\n--- read_ndef() ---")
    uid = reader.get_uid()
    nfc_tag = reader.read_ndef(uid=uid)
    if nfc_tag is not None:
        print(f"  ID:          {nfc_tag.id}")
        print(f"  Name:        {nfc_tag.name}")
        print(f"  Description: {nfc_tag.description}")
        if nfc_tag.data:
            for d in nfc_tag.data:
                print(f"  {d.magnitude}: {d.value} {d.unit_short}")
        else:
            print("  No sensor data parsed")
    else:
        print("  Could not read NDEF")
    return nfc_tag


def test_read_tag_index(reader):
    print("\n--- read_tag_index() ---")
    idx = reader.read_tag_index()
    if idx is not None:
        print(f"  Index (uint32): {idx}")
    else:
        print("  Could not read index")
    return idx


def test_read_bulk_data(reader):
    print("\n--- read_bulk_data() ---")
    values = reader.read_bulk_data()
    if values:
        print(f"  Total uint16 values: {len(values)}")
        print(f"  First 20: {values[:20]}")
    else:
        print("  Could not read bulk data")
    return values


def test_set_ndef_mode(reader):
    print("\n--- set_ndef_mode() ---")
    ok = reader.set_ndef_mode()
    print(f"  Result: {'OK' if ok else 'FAIL'}")
    return ok


def test_set_bulk_mode(reader):
    print("\n--- set_bulk_mode() ---")
    ok = reader.set_bulk_mode()
    print(f"  Result: {'OK' if ok else 'FAIL'}")
    return ok


def test_write_read_back(reader, block=48):
    test_data = [0xDE, 0xAD, 0xBE, 0xEF]
    print(f"\n--- write_data(block={block}, data={bytes_to_hex(test_data)}) ---")
    ok = reader.write_data(block, test_data)
    print(f"  Write: {'OK' if ok else 'FAIL'}")
    if ok:
        readback = reader.read_data(block, 1)
        print(f"  Read back: {bytes_to_hex(readback)}")
        if readback and list(readback[:4]) == test_data:
            print("  Verification OK")
        else:
            print("  Verification FAILED - data mismatch")
    return ok


# ---------------------------------------------------------------------------
# Full test sequence
# ---------------------------------------------------------------------------

def run_full_test(reader):
    print("\n" + "=" * 60)
    print("  RUNNING FULL TEST")
    print("=" * 60)

    # 1. RF ON
    test_turn_on_field(reader)
    sleep(0.3)

    # 2. UID
    uid = test_get_uid(reader)
    if uid is None:
        print("\n  No tag present. Place a tag and try again.")
        return

    # 3. NDEF mode - read message
    test_set_ndef_mode(reader)
    sleep(0.3)
    test_turn_on_field(reader)
    sleep(0.3)
    test_read_ndef(reader)

    # 4. BULK mode - read index and data
    test_set_bulk_mode(reader)
    sleep(0.3)
    test_turn_on_field(reader)
    sleep(0.3)
    test_read_tag_index(reader)
    test_read_bulk_data(reader)

    # 5. Write/read test
    test_write_read_back(reader, block=48)

    # 6. Back to NDEF
    test_set_ndef_mode(reader)

    print("\n" + "=" * 60)
    print("  FULL TEST COMPLETE")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

def print_menu():
    print("\n" + "=" * 60)
    print("  TEST ACR1552 (High-Level) - Menu")
    print("=" * 60)
    print("  1. Turn ON RF field")
    print("  2. Turn OFF RF field")
    print("  3. Read tag UID")
    print("  4. Read arbitrary block(s)")
    print("  5. Read NDEF message")
    print("  6. Read BULK index")
    print("  7. Read BULK data")
    print("  8. Set BULK mode")
    print("  9. Set NDEF mode")
    print(" 10. Write and verify test block")
    print(" 11. Run full test sequence")
    print("  0. Exit")
    print("-" * 60)


def run_interactive(reader):
    while True:
        print_menu()
        try:
            choice = input("Select option: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            test_turn_on_field(reader)
        elif choice == "2":
            test_turn_off_field(reader)
        elif choice == "3":
            test_get_uid(reader)
        elif choice == "4":
            try:
                sb = int(input("  Start block: "))
                nb = int(input("  Number of blocks: "))
                test_read_data(reader, sb, nb)
            except ValueError:
                print("  Invalid input")
        elif choice == "5":
            test_read_ndef(reader)
        elif choice == "6":
            test_read_tag_index(reader)
        elif choice == "7":
            test_read_bulk_data(reader)
        elif choice == "8":
            test_set_bulk_mode(reader)
        elif choice == "9":
            test_set_ndef_mode(reader)
        elif choice == "10":
            test_write_read_back(reader)
        elif choice == "11":
            run_full_test(reader)
        elif choice == "0":
            break
        else:
            print("  Invalid option")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Scanning for ACR1552 reader...")
    scanner = SenseidReaderScanner(autostart=True)
    connection_info = scanner.wait_for_reader_of_type(SupportedSenseidReader.ACR1552, timeout_s=10)

    if connection_info is None:
        print("No ACR1552 reader found. Is it connected?")
        exit(1)

    print(f"Found reader: {connection_info.connection_string}")
    sid_reader = create_SenseidReader(connection_info)
    sid_reader.connect(connection_info.connection_string)
    scanner.stop()

    try:
        run_interactive(sid_reader)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        print("\nDisconnecting...")
        try:
            sid_reader.turn_on_field()
            sid_reader.disconnect()
        except Exception:
            pass
        print("Done.")
