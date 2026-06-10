      *================================================================
      * COPYBOOK : CRCUSTAC.cpy
      * SYSTEM   : Credit Risk Behaviour Scoring System
      * PURPOSE  : Customer Account Master record layout
      *            Maps to DB2 table CRISK.CUST_ACCOUNT_MASTER
      *            and to Oracle external table XML field structure
      *================================================================
       01  CR-CUST-ACCOUNT-REC.
           05  CRA-EXTERNAL-ACCT-NUM   PIC X(20).
      *        Maps to: DB2 EXTERNAL_ACCOUNT_NUMBER
      *        XML tag: <external_account_number>
      *        Oracle : MAIN_ACCOUNT_NUMBER
           05  CRA-SUB-ACCOUNT-NUM     PIC X(10).
      *        Maps to: DB2 SUB_ACCOUNT_NUMBER
      *        XML tag: <sub_no>
      *        Oracle : SUB_ACCOUNT_NUMBER
           05  CRA-BOOK-ID             PIC X(6).
      *        Maps to: DB2 BOOK_ID (company/portfolio code)
      *        XML tag: <book_id>
      *        Oracle : COMPANY
           05  CRA-CUSTOMER-ID         PIC X(15).
      *        Maps to: DB2 CUSTOMER_ID (internal key)
           05  CRA-PRODUCT-TYPE        PIC X(4).
      *        Maps to: DB2 PRODUCT_TYPE
      *        Values: LOAN, MORT, CRED, CURR
           05  CRA-RISK-SEGMENT        PIC X(3).
      *        Maps to: DB2 RISK_SEGMENT (A01-Z99)
           05  CRA-BEHAVIOUR-SCORE     PIC S9(4) COMP.
      *        Maps to: DB2 BEHAVIOUR_SCORE (0-999)
           05  CRA-UNSECURED-IND       PIC X(1).
      *        Maps to: DB2 UNSECURED_IND (Y/N)
      *        XML tag: <unsec_ind>
      *        Oracle : UNSECURED
           05  CRA-ACCOUNT-OPEN-DATE   PIC X(8).
      *        Maps to: DB2 ACCOUNT_OPEN_DATE (YYYYMMDD)
           05  CRA-NEW-MAIN-ACCT-NUM   PIC X(20).
      *        Maps to: DB2 NEW_MAIN_ACCOUNT_NUMBER
      *        XML tag: <New_Main_Account_Number>
      *        Oracle : NEW_MAIN_ACC_NUM
           05  CRA-NEW-LOAN-ACCT-NUM   PIC X(20).
      *        Maps to: DB2 NEW_LOAN_ACCOUNT_NUMBER
      *        XML tag: <New_Loan_Account_Number>
      *        Oracle : NEW_LOAN_ACC_NUM
           05  CRA-PROCESS-DATE        PIC X(8).
      *        Maps to: DB2 PROCESS_DATE (YYYYMMDD)
           05  FILLER                  PIC X(13).
