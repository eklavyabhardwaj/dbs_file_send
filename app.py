#!/usr/bin/env python3

import requests
import pandas as pd
from datetime import datetime
import json
import subprocess
import os

def import_public_key(file_path="DSGJPMUAT-Public.asc"):
    """
    Imports a public key from a given file path into the GPG keyring.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    print(f"Importing the public key from '{file_path}' into the GPG keyring...")
    result = subprocess.run(
        ["gpg", "--import", file_path],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print("Key import succeeded.")
    else:
        print("Key import failed!")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        raise RuntimeError("GPG key import failed.")

def fetch_data_from_erp():
    """
    Fetch Payment Orders from ERPNext.
    Adjust URL, token, filters, fields, etc. as necessary.
    """
    base_url = 'https://erpv14.electrolabgroup.com/'
    endpoint = 'api/resource/Payment Order'
    url = base_url + endpoint

    headers = {
        'Authorization': 'token 3ee8d03949516d0:6baa361266cf807'  # Replace with valid token
    }

    limit_start = 0
    limit_page_length = 1000
    all_data = []
    today_date = datetime.today().strftime('%Y-%m-%d')

    while True:
        params = {
            'fields': json.dumps([
                "naming_series", "company", "payment_order_type", "party", "posting_date",
                "company_bank", "company_bank_account", "account", "references.reference_name",
                "references.amount", "references.supplier", "references.payment_request",
                "references.mode_of_payment", "references.bank_account", "references.account",
                "references.payment_reference"
            ]),
            'filters': json.dumps([
                ["company_bank_account", "=", "DBS Bank Limited - INR"],
                ["posting_date", "=", today_date]
            ]),
            'limit_start': limit_start,
            'limit_page_length': limit_page_length
        }

        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            fetched_data = data.get('data', [])

            if not fetched_data:
                print("All data has been fetched.")
                break

            all_data.extend(fetched_data)
            limit_start += limit_page_length
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
            print("Response:", response.json())
            break

    return all_data

def create_local_text_file(payment_orders, local_filename):
    """
    Creates a structured text file with HEADER, PAYMENT lines, and TRAILER.
    """
    today_date = datetime.today().strftime('%Y-%m-%d')
    df = pd.DataFrame(payment_orders)

    # HEADER
    header = f"HEADER,{today_date},INELTR01,Electrolab India Pvt. Ltd.\n"

    # PAYMENT lines
    payments = []
    for item in payment_orders:
        reference_name   = item.get('reference_name', "")
        mode_of_payment  = item.get('mode_of_payment', "")
        posting_date     = item.get('posting_date', "")
        party            = item.get('party', "")
        bank_account     = item.get('bank_account', "")
        amount           = item.get('amount', 0.0)

        payment_line = (
            f"PAYMENT,{mode_of_payment},DBS Bank Limited,INR,{reference_name},"
            f"INR,00001,{posting_date},,,{party},,,,{bank_account},,,,,{amount},"
            f",,,,,,{mode_of_payment},,,,,,,,{party},,,,,,,eklavyabhardwaj@electrolabgroup.com,,,,,,,"
            f" REFERNCEXX,,,,\n"
        )
        payments.append(payment_line)

    # TRAILER
    total_count = len(payments)
    total_amount = sum(float(item.get('amount', 0.0)) for item in payment_orders)
    trailer = f"TRAILER,{total_count},{total_amount}\n"

    # Combine into a single string
    full_text_file = header + "".join(payments) + trailer

    # Write to file
    with open(local_filename, 'w') as file:
        file.write(full_text_file)

    print(f"File '{local_filename}' created successfully with {len(payments)} payment lines.")

def encrypt_file_gpg(input_file):
    """
    Encrypts `input_file` using GPG, saving as `input_file + ".pgp"`.
    The recipient is determined by the imported public key.
    """
    output_file = input_file + ".pgp"
    recipient = "DSGJPMUAT"  # Replace with the actual UID from the imported public key if necessary.

    cmd = [
        "gpg",
        "--output", output_file,
        "--encrypt",
        "--recipient", recipient,
        input_file
    ]

    print(f"Encrypting '{input_file}' to '{output_file}' for recipient '{recipient}' ...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"File successfully encrypted to: {output_file}")
    else:
        print("GPG encryption failed!")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        raise RuntimeError("Encryption failed")

    return output_file

def upload_file_sftp(local_file, remote_file, remote_dir="Outbox"):
    """
    Uploads `local_file` to `remote_file` in `remote_dir` via SFTP,
    using '-F /tmp/my_ssh_config'.
    """
    sftp_host = "INELTR01@45.65.2.71"
    sftp_config = "/tmp/my_ssh_config"
    batch_file = "sftp_batch.txt"

    commands = f"""
cd {remote_dir}
put {local_file} {remote_file}
bye
"""
    with open(batch_file, 'w') as bf:
        bf.write(commands)

    print(f"Uploading '{local_file}' to '{remote_dir}/{remote_file}' on {sftp_host}...")
    result = subprocess.run(
        ["sftp", "-F", sftp_config, "-b", batch_file, sftp_host],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"File '{local_file}' uploaded successfully to '{remote_dir}/{remote_file}'.")
    else:
        print("Failed to upload file via sftp.")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        raise RuntimeError("SFTP upload failed")

def main():
    # A) Import the public key from file
    import_public_key("DSGJPMUAT-Public.asc")

    # B) Fetch ERPNext data
    payment_orders = fetch_data_from_erp()

    # C) Our desired plaintext file name includes ".TXT."
    original_file = "UFF2.FORMAT362.INELTR01.INELTR01.311220241431.TXT.DBSSINBB"
    create_local_text_file(payment_orders, original_file)

    # D) Encrypt => final name: "UFF2.FORMAT362.INELTR01.INELTR01.271220241428.TXT.DBSSINBB.pgp"
    encrypted_file = encrypt_file_gpg(original_file)

    # E) Upload the .pgp file
    upload_file_sftp(
        local_file=encrypted_file,
        remote_file=os.path.basename(encrypted_file),
        remote_dir="Outbox"
    )

if __name__ == "__main__":
    main()