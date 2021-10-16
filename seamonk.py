import os
import subprocess
import time
import datetime
import json
import cardanotx as tx
from sys import exit, argv
from os.path import isdir, isfile

def deposit(profile_name, log, cache, watch_addr, watch_skey_path, smartcontract_addr, token_policy_id, token_name, deposit_amt, sc_ada_amt, ada_amt, datum_hash, collateral):
    # Begin log file
    runlog_file = log + 'run.log'
    
    # Clear the cache
    tx.clean_folder(cache)
    tx.proto(profile_name, cache)
    tx.get_utxo(profile_name, watch_addr, cache, 'utxo.json')
    
    # Get wallet utxos
    utxo_in, utxo_col, tokens, flag, _ = tx.get_txin(log, cache, 'utxo.json', collateral)
    
    # Build, sign, and send transaction
    if flag is True:
        _, until_tip, block = tx.get_tip(profile_name, cache)
        
        # Calculate token quantity and any change
        tok_bal = 0
        sc_out = int(deposit_amt)
        tok_new = 0
        for token in tokens:
            if token == 'lovelace':
                continue
            for t_qty in tokens[token]:
                tok_bal = tokens[token][t_qty]
                tok_new = tok_bal - sc_out

        # Setup UTxOs
        tx_out = tx.process_tokens(profile_name, cache, tokens, watch_addr, 'all', ada_amt, [token_policy_id, token_name]) # Account for all except token to swap
        tx_out += ['--tx-out', watch_addr + '+' + str(collateral)] # UTxO to replenish collateral
        if tok_new > 0:
            tx_out += tx.process_tokens(profile_name, cache, tokens, watch_addr, tok_new, ada_amt) # Account for deposited-token change (if any)
        tx_out += tx.process_tokens(profile_name, cache, tokens, smartcontract_addr, sc_out, sc_ada_amt, [token_policy_id, token_name], False) # Send just the token for swap
        print('\nTX Out Settings: ', tx_out)
        tx_data = [
            '--tx-out-datum-hash', datum_hash # This has to be the hash of the fingerprint of the token
        ]
        print('\nDatum: ', tx_data)
        tx.build_tx(profile_name, log, cache, watch_addr, until_tip, utxo_in, utxo_col, tx_out, tx_data)
        
        # Sign and submit the transaction
        witnesses = [
            '--signing-key-file',
            watch_skey_path
        ]
        tx.sign_tx(profile_name, log, cache, witnesses)
        tx.submit_tx(profile_name, log, cache)
        exit(0)
    else:
        print("No collateral UTxO found! Please create a UTxO of 2 ADA (2000000 lovelace) before trying again.")
        exit(0)

def smartcontractswap(profile_name, log, cache, watch_addr, watch_skey_path, smartcontract_addr, smartcontract_path, token_policy_id, token_name, datum_hash, recipient_addr, token_qty, return_ada, price,  collateral):
    # Begin log file
    runlog_file = log + 'run.log'

    # Clear the cache
    tx.clean_folder(cache)
    tx.proto(profile_name, cache)
    tx.get_utxo(profile_name, watch_addr, cache, 'utxo.json')
    
    # Run get_txin
    utxo_in, utxo_col, tokens, flag, _ = tx.get_txin(log, cache, 'utxo.json', collateral)
    
    # Build, Sign, and Send TX
    if flag is True:
        tx.get_utxo(profile_name, smartcontract_addr, cache, 'utxo_script.json')
        if isfile(cache+'utxo_script.json') is False:
            with open(runlog_file, 'a') as runlog:
                runlog.write('\nERROR: Could not file utxo_script.json\n')
                runlog.close()
            exit(0)
        _, _, sc_tokens, _, data_list = tx.get_txin(log, cache, 'utxo_script.json', collateral, True, datum_hash)
        contract_utxo_in = utxo_in
        for key in data_list:
            # A single UTXO with a single datum can be spent
            if data_list[key] == datum_hash:
                contract_utxo_in += ['--tx-in', key]
                break
        _, until_tip, block = tx.get_tip(profile_name, cache)
        # Calculate token quantity and change
        sc_bal = 0
        sc_out = int(token_qty)
        sc_new = 0
        for token in sc_tokens:
            # lovelace will be auto accounted for using --change-address
            if token == 'lovelace':
                continue
            for t_qty in sc_tokens[token]:
                sc_bal = sc_tokens[token][t_qty]
                sc_new = sc_bal - sc_out
        tx_out = tx.process_tokens(profile_name, cache, sc_tokens, recipient_addr, sc_out, return_ada) # UTxO to Send Token(s) to the Buyer
        tx_out += tx.process_tokens(profile_name, cache, tokens, watch_addr) # Change
        tx_out += ['--tx-out', watch_addr + '+' + str(collateral)] # Replenish collateral
        if price:
            tx_out += ['--tx-out', watch_addr + '+' + str(price)] # UTxO for price if set to process price payment
        if sc_new > 0:
            tx_out += tx.process_tokens(profile_name, cache, sc_tokens, smartcontract_addr, sc_new) # UTxO to Send Change to Script - MUST BE LAST UTXO FOR DATUM
        tx_data = [
            '--tx-out-datum-hash', datum_hash,
            '--tx-in-datum-value', '"{}"'.format(tx.get_token_identifier(token_policy_id, token_name)),
            '--tx-in-redeemer-value', '""',
            '--tx-in-script-file', smartcontract_path
        ]
        tx.build_tx(profile_name, log, cache, watch_addr, until_tip, contract_utxo_in, utxo_col, tx_out, tx_data)
        
        witnesses = [
            '--signing-key-file',
            watch_skey_path
        ]
        tx.sign_tx(profile_name, log, cache, witnesses)
        tx.submit_tx(profile_name, log, cache)
    else:
        with open(runlog_file, 'a') as runlog:
            runlog.write('\nNo collateral UTxO found! Please create a UTxO of 2 ADA (2000000 lovelace) before trying again.\n')
            runlog.close()
        exit(0)

def start_deposit(profile_name, log, cache, watch_addr, watch_skey_path, watch_vkey_path, watch_key_hash, smartcontract_path, token_policy_id, token_name, collateral):
    # Begin log file
    runlog_file = log + 'run.log'

    smartcontract_addr = tx.get_smartcontract_addr(profile_name, smartcontract_path)

    print("\n--- NOTE: Proceed Only If You Are Depositing Your NFT or Tokens Into the NFT/Token Swap Smart Contract ---\n")
    print("\n---       Be sure you have at least 1 UTxO in your wallet with 2 ADA for collateral before running this.   ---\n")
    print("\n-----------------------------\n| Please Verify Your Input! |\n-----------------------------\n")
    print("\nMy Watched Wallet Address >> ",watch_addr)
    print("\nMy Address PubKey Hash (for smartcontract validation) >> ",str(watch_key_hash))
    print("\nMy Watched Addresses skey File Path >> ",watch_skey_path)
    print("\nSmartContract Address >> ",smartcontract_addr)
    print("\nNative Token Policy ID >> ",token_policy_id)
    print("\nNative Token Name >> ",token_name)
    
    
    verify = input("\n\nIs the information above correct AND you have a 2 ADA UTxO for Collateral? (yes or no): ")
    
    if verify == ("yes"):
        print("\n\nContinuing . . . \n")
    elif verify == ("no"):
        print("\n\nQuitting, please run again to try again!\n\n")
        exit(0)
    
    deposit_amt = input("\nHow many " + token_name + " tokens are you depositing?\nDeposit Amount:")
    sc_ada_amt = input("\nHow many lovelace to include with token(s) at SmartContract UTxO? (must be at least protocol minimum for token(s))\nLovelace Amount SmartContract:")
    ada_amt = input("\nHow many lovelace to include with token(s) at watched address UTxO(s)? (must be at least protocol minimum for token(s))\nLovelace Amount Wallet:")

    # Calculate the "fingerprint"
    FINGERPRINT = tx.get_token_identifier(token_policy_id, token_name) # Not real fingerprint but works
    DATUM_HASH  = tx.get_hash_value(profile_name, '"{}"'.format(FINGERPRINT)).replace('\n', '')
    #print('Datum Hash: ', DATUM_HASH)
    deposit(profile_name, log, cache, watch_addr, watch_skey_path, smartcontract_addr, token_policy_id, token_name, deposit_amt, sc_ada_amt, ada_amt, DATUM_HASH, collateral)

def create_smartcontract(profile_name, sc_path, src, pubkeyhash, price):
    # Replace the validator options
    template_src = src + 'src/' + 'template_SwapToken.hs'
    output_src = src + 'src/' + 'SwapToken.hs'
    with open(template_src, 'r') as smartcontract :
        scdata = smartcontract.read()
        smartcontract.close()
    scdata = scdata.replace('PUBKEY_HASH010101010101010101010101010101010101010101010', ' '.join(pubkeyhash.split()))
    scdata = scdata.replace('PRICE_00000000000000', ' '.join(price.split()))
    with open(output_src, 'w') as smartcontract:
        smartcontract.write(scdata)
        smartcontract.close()
    
    # Compile the plutus smartcontract
    approot = os.path.realpath(os.path.dirname(__file__))
    os.chdir(src)
    print("\nPlease wait while your SmartContract source is being compiled, this may take a few minutes . . .\n\n")
    time.sleep(5)
    data_build = subprocess.call(['cabal', 'build'], stdout = subprocess.PIPE)
    print('\nGenerating SmartContract Plutus Script . . .')
    data_run = subprocess.call(['cabal', 'run'], stdout = subprocess.PIPE)
    print("\nCheck the above output for any errors.")

    # Move the plutus file to the working directory
    os.replace(src + 'swaptoken.plutus', sc_path)
    sc_addr = get_smartcontract_addr(profile_name, sc_path)
    print('\n================ Finished! ================\n > Your SmartContract Address Is: ' + sc_addr)
    exit(0)

def setup(logroot, profile_name='', reconfig=False, append=False):
    if reconfig:
        UNIQUE_NAME = profile_name
        print('\n!!! WARNING !!!\nSettings for profile "' + profile_name + '" are about to be overwritten!\n\nExit now if you do not want to do that.\n\n')
    print('\n========================= Setting Up New Profile =========================\n')
    print('\n*IMPORTANT NOTES*\n')
    print('If this is the first time running the setup a profile.json file will be')
    print('created within this working directory. If this is a new profile addition,')
    print('it will be added to the json of the profile.json file and should be called')
    print('with the profile option like so: `python3 seamonk.py profile=MyProfileName`')
    print('where MyProfileName is the name you give this profile.')
    print('\nFor new profiles, this will also generate a whitelist.txt file within the')
    print('profiles directory, under the directory named after this profile,')
    print('e.g. profiles/MyProfileName/whitelist.txt. Please add the Cardano addresses')
    print('you would like whitelisted to this file, each on a new line. Note that only')
    print('1 address from each whitelisted wallet with a complex 103-length address')
    print('need be added and the entire wallet will be whitelisted.\n')
    if not reconfig:
        UNIQUE_NAME = input('\nEnter A Unique Profile Name For This Profile\n(no spaces, e.g. CypherMonk_NFT_Sale)\n >Unique Name:')
    NETWORKINPUT = input('\nNetwork Type (enter either mainnet or testnet)\n >Network Type:')
    if NETWORKINPUT == 'testnet':
        MAGICINPUT = input(' >Testnet Magic:')
    CLI_PATH = input('\nExplicit Path To "cardano-cli"\n(leave empty if cardano-cli is in your system path and\nit is the version you want to use with this profile)\n >Cardano-CLI Path:')
    API_ID = input('\nYour Blockfrost API ID\n(should match the network-specific ID i.e. mainnet vs testnet)\n >Blockfrost API ID:')
    WATCH_ADDR = input('\nWallet Address To Watch For Transactions/Payments\n(this is the address you provide to users or customers)\n >Watch Address:')
    WATCH_SKEY_PATH = input('\nSigning Key File Path Of Watch Address\n(e.g. /home/user/node/wallets/watch.skey)\n >Watch Address .skey File Path:')
    WATCH_VKEY_PATH = input('\nVerification Key File Path Of Watch Address\n(e.g. /home/user/node/wallet/watch.vkey)\n >Watch Address .vkey File Path:')
    SMARTCONTRACT_PATH = input('\nSmart Contract Plutus File Path\n(path to the ".plutus" file - leave blank if you will be using the built-in simple token swap contract)\n >Smart Contract File Path:')
    TOKEN_POLICY_ID = input('\nToken Policy ID Of Token To Be Deposited To Smart Contract\n(the long string before the dot)\n >Token Policy ID:')
    TOKEN_NAME = input('\nToken Name Of Token To Be Deposited To Smart Contract\n(comes after the dot after the policy ID)\n >Token Name:')
    TOKEN_QTY = input('\nToken Quantity To Be Sent In Each Swap Transaction\n(how many tokens to send with each successful matched transaction swap)\n >Token Amount To Swap Per TX:')
    print('\n\nNOTE: The following amount responses should all be\n      entered in Lovelace e.g. 1.5 ADA = 1500000\n\n')
    RETURN_ADA = input('\nAmount Of Lovelace To Include With Each Swap Transaction\n(cannot be below protocol limit)\n >Included ADA Amount in Lovelace:')
    EXPECT_ADA = input('\nAmount Of Lovelace To Watch For\n(this is the amount SeaMonk is watching the wallet for)\n >Watch-for Amount in Lovelace:')
    PRICE = input('\nPrice If Any To Be Paid To Watch Address\n(this is not the amount being watched for)\n >Price Amount in Lovelace:')
    COLLATSTRING = input('\nAmount Of Lovelace Collateral To Include\n(required for smartcontract tx, usually 2000000)\n >Collateral Amount in Lovelace:')
    CHECKSTRING = input('\nCheck for Transactions In Same Instance, Between Payment Processing?\n(Recommended: False - and run a seperate instance for getting transactions)\n >Enter True or False:')
    WLONESTRING = input('\nRemove A Sender Address From Whitelist After 1 Payment is Received?\n >Enter True or False:')
    
    # Setup profile-specific cache and log folders
    log = os.path.join(os.path.join(logroot, UNIQUE_NAME), '')
    cache = os.path.join(os.path.join(log, 'cache'), '')
    try:
        os.mkdir(log)
        os.mkdir(cache)
    except OSError:
        pass

    # Process inputs
    if len(CLI_PATH) == 0:
        CLI_PATH = 'cardano-cli'
    WATCH_KEY_HASH = tx.get_address_pubkeyhash(CLI_PATH, WATCH_VKEY_PATH)
    if len(SMARTCONTRACT_PATH) == 0:
        SMARTCONTRACT_PATH = log + UNIQUE_NAME + '.plutus'
    NETWORK = 'mainnet'
    MAGIC = ''
    API_URI = 'https://cardano-mainnet.blockfrost.io/api/v0/'
    if NETWORKINPUT == 'testnet':
        NETWORK = 'testnet-magic'
        MAGIC = MAGICINPUT
        API_URI = 'https://cardano-testnet.blockfrost.io/api/v0/'
    COLLATERAL = int(COLLATSTRING)
    CHECK = False
    USE_WHITELIST = False
    WHITELIST_ONCE = False
    if CHECKSTRING == 'True' or CHECKSTRING == 'true':
        CHECK = True
    if WLONESTRING == 'True' or WLONESTRING == 'true':
        WHITELIST_ONCE = True

    # Save to dictionary
    rawSettings = {'network':NETWORK,'magic':MAGIC,'cli_path':CLI_PATH,'api_uri':API_URI,'api':API_ID,'watchaddr':WATCH_ADDR,'collateral':COLLATERAL,'check':CHECK,'wlone':WHITELIST_ONCE,'watchskey':WATCH_SKEY_PATH,'watchvkey':WATCH_VKEY_PATH,'watchkeyhash':WATCH_KEY_HASH,'scpath':SMARTCONTRACT_PATH,'tokenid':TOKEN_POLICY_ID,'tokenname':TOKEN_NAME,'expectada':EXPECT_ADA,'price':PRICE,'tokenqty':TOKEN_QTY,'returnada':RETURN_ADA}

    # Save/Update whitelist and profile.json files
    settings_file = 'profile.json'
    is_set_file = os.path.isfile(settings_file)
    if not is_set_file:
        open(settings_file, 'x')
    if not append:
        if reconfig:
            reconfig_profile = json.load(open(settings_file, 'r'))
            reconfig_profile[UNIQUE_NAME] = rawSettings
            jsonSettings = json.dumps(reconfig_profile)
        else:
            writeSettings = {UNIQUE_NAME:rawSettings}
            jsonSettings = json.dumps(writeSettings)
    else:
        append_profile = json.load(open(settings_file, 'r'))
        append_profile[UNIQUE_NAME] = rawSettings
        jsonSettings = json.dumps(append_profile)
    with open(settings_file, 'w') as s_file:
        s_file.write(jsonSettings)
        s_file.close()

    # Setup and save whitelist file
    whitelist_file = log + 'whitelist.txt'
    is_wl_file = os.path.isfile(whitelist_file)
    if not is_wl_file:
        try:
            open(whitelist_file, 'x')
        except OSError:
            pass

    print('\n\n=========================     Profile Saved      =========================\nIf using more than 1 profile, run with this explicit profile with option\n"profile=' + UNIQUE_NAME + '" e.g. `python3 seamonk.py profile=' + UNIQUE_NAME + '`.\n\nExiting . . . \n')
    exit(0)


if __name__ == "__main__":
    # Setup Temp Directory (try to)
    scptroot = os.path.realpath(os.path.dirname(__file__))
    SRC = os.path.join(os.path.join(scptroot, 'smartcontract-src'), '')

    logname = 'profiles'
    logpath = os.path.join(scptroot, logname)
    LOGROOT = os.path.join(logpath, '')

    try:
        os.mkdir(logname)
    except OSError:
        pass
   
    # Setup Settings Dictionary
    settings_file = 'profile.json'
    is_settings_file = os.path.isfile(settings_file)
    if not is_settings_file:
        setup(LOGROOT)
    
    # Get any set profile name
    PROFILE_NAME = ''
    if len(argv) > 1:
        INPUT = argv[1]
        if INPUT.startswith('profile='):
            PROFILE_NAME = INPUT[8:]

    # Load settings
    load_profile = json.load(open(settings_file, 'r'))
    if len(PROFILE_NAME) == 0:
        PROFILE_NAME = list(load_profile.keys())[0]
    PROFILE = load_profile[PROFILE_NAME]
    API_ID = PROFILE['api']
    WATCH_ADDR = PROFILE['watchaddr']
    COLLATERAL = PROFILE['collateral']
    CHECK = PROFILE['check']
    WHITELIST_ONCE = PROFILE['wlone']
    WATCH_SKEY_PATH = PROFILE['watchskey']
    WATCH_VKEY_PATH = PROFILE['watchvkey']
    WATCH_KEY_HASH = PROFILE['watchkeyhash']
    SMARTCONTRACT_PATH = PROFILE['scpath']
    TOKEN_POLICY_ID = PROFILE['tokenid']
    TOKEN_NAME = PROFILE['tokenname']
    EXPECT_ADA = PROFILE['expectada']
    PRICE = PROFILE['price']
    TOKEN_QTY = PROFILE['tokenqty']
    RETURN_ADA = PROFILE['returnada']

    # Input before settings load
    if len(argv) > 1:
        if argv[1] == 'reconfigure':
            setup(LOGROOT, PROFILE_NAME, True)
        if argv[1] == 'new_profile':
            setup(LOGROOT, PROFILE_NAME, False, True)

    # Instantiate log and cache folders for profile
    PROFILELOG = os.path.join(os.path.join(LOGROOT, PROFILE_NAME), '')
    PROFILECACHE = os.path.join(os.path.join(PROFILELOG, 'cache'), '')

    # Instantiate log for profile
    runlog_file = PROFILELOG + 'run.log'
    is_runlog_file = os.path.isfile(runlog_file)
    if not is_runlog_file:
        try:
            open(runlog_file, 'x')
        except OSError:
            pass
    with open(runlog_file, 'a') as runlog:
        time_now = datetime.datetime.now()
        runlog.write('\nNew Run at: ' + str(time_now))
        runlog.close()

    # Check for smartcontract file and prompt to create if not found
    sc_file = SMARTCONTRACT_PATH
    is_sc_file = os.path.isfile(sc_file)
    if not is_sc_file:
        create_smartcontract(PROFILE_NAME, SMARTCONTRACT_PATH, SRC, WATCH_KEY_HASH, PRICE)

    # Check for watched wallet signing key file
    if isfile(WATCH_SKEY_PATH) is False:
        print('The file:', WATCH_SKEY_PATH, 'could not be found.')
        exit(0)

    if len(argv) > 1 and len(API_ID) > 1 and len(WATCH_ADDR) > 1:
        INPUT = argv[1]

        if INPUT == 'create_smartcontract':
            create_smartcontract(PROFILE_NAME, SMARTCONTRACT_PATH, SRC, WATCH_KEY_HASH, PRICE)

        if INPUT == 'get_transactions':
            while True:
                result_tx = tx.log_new_txs(PROFILE_NAME, PROFILELOG, API_ID, WATCH_ADDR)
                time.sleep(5)

        if INPUT == 'deposit':
            start_deposit(PROFILE_NAME, PROFILELOG, PROFILECACHE, WATCH_ADDR, WATCH_SKEY_PATH, WATCH_VKEY_PATH, WATCH_KEY_HASH, SMARTCONTRACT_PATH, TOKEN_POLICY_ID, TOKEN_NAME, COLLATERAL)

    # Calculate the "fingerprint" and finalize other variables
    FINGERPRINT = tx.get_token_identifier(TOKEN_POLICY_ID, TOKEN_NAME)
    DATUM_HASH  = tx.get_hash_value(PROFILE_NAME, '"{}"'.format(FINGERPRINT)).replace('\n', '')
    SMARTCONTRACT_ADDR = tx.get_smartcontract_addr(PROFILE_NAME, SMARTCONTRACT_PATH)
    
    # TESTING
    """
    print("profile loaded: " + PROFILE_NAME)
    print("profile settings loaded: log=" + PROFILELOG + " | cache=" + PROFILECACHE + " | api_id=" + API_ID + " | watch_addr=" + WATCH_ADDR + " | collateral=" + str(COLLATERAL) + " | check=" + str(CHECK) + " | whitelist_once=" + str(WHITELIST_ONCE) + " | skey=" + WATCH_SKEY_PATH + " | vkey=" + WATCH_VKEY_PATH + " | pubkey_hash="+WATCH_KEY_HASH+" | sc_path=" + SMARTCONTRACT_PATH + " | token_id=" + TOKEN_POLICY_ID + " | token_name=" + TOKEN_NAME + " | watch_for=" + EXPECT_ADA + " | price=" + PRICE + " | token_qty=" + TOKEN_QTY+ " | return_ada=" + RETURN_ADA)
    print("Additional settings:")
    print(load_profile[PROFILE_NAME]['cli_path'])
    print(load_profile[PROFILE_NAME]['network'])
    print(load_profile[PROFILE_NAME]['magic'])
    print(load_profile[PROFILE_NAME]['api_uri'])
    exit(0)
    """
    # END

    # Begin main payment checking/recording loop here
    while True:
        #print("starting loop, waiting a few seconds")
        time.sleep(10)

        # Check for payment, initiate Smart Contract on success
        # Only run payment check if new transactions are recorded
        if CHECK:
            result_tx = tx.log_new_txs(PROFILE_NAME, PROFILELOG, API_ID, WATCH_ADDR)
            with open(runlog_file, 'a') as runlog:
                runlog.write('New txs to compare: '+str(result_tx)+'\n')
                runlog.close()
            #print("new txs gathered: "+str(result_tx)+"\n")
        
        time.sleep(10)
        result = 'none'

        whitelist_file = os.path.join(os.path.realpath(os.path.dirname(__file__)), 'whitelist.txt')
        is_whitelist_file = os.path.isfile(whitelist_file)
        if not is_whitelist_file:
            with open(runlog_file, 'a') as runlog:
                runlog.write('Missing expected file: whitelist_nft.txt in this same folder!\n')
                runlog.close()
            exit(0)
        whitelist_r = open(whitelist_file, 'r')
        windex = 0
        # Foreach line of the whitelist file
        for waddr in whitelist_r:
            windex += 1
            if not EXPECT_ADA:
                EXPECT_ADA = 0
            RECIPIENT_ADDR = waddr.strip()
            result = tx.check_for_payment(PROFILE_NAME, PROFILELOG, API_ID, WATCH_ADDR, EXPECT_ADA, RECIPIENT_ADDR)
            if len(result) < 1:
                with open(runlog_file, 'a') as runlog:
                    runlog.write('No new payments detected\n')
                    runlog.close()
                continue
            if WHITELIST_ONCE:
                clean_wlws = RECIPIENT_ADDR
                with open(whitelist_file,'r') as read_file:
                    lines = read_file.readlines()
                currentLine = 0
                with open(whitelist_file,'w') as write_file:
                    for line in lines:
                        if line.strip('\n') != clean_wlws:
                            write_file.write(line)
                read_file.close()
                write_file.close()
            with open(runlog_file, 'a') as runlog:
                runlog.write('Running whitelist for addr: '+RECIPIENT_ADDR+' | '+str(EXPECT_ADA)+'\n')
                runlog.close()
            # Run swap on matched tx
            smartcontractswap(PROFILE_NAME, PROFILELOG, PROFILECACHE, WATCH_ADDR, WATCH_SKEY_PATH, SMARTCONTRACT_ADDR, SMARTCONTRACT_PATH, TOKEN_POLICY_ID, TOKEN_NAME, DATUM_HASH, RECIPIENT_ADDR, TOKEN_QTY, RETURN_ADA, PRICE, COLLATERAL)
            time.sleep(300)
        whitelist_r.close()