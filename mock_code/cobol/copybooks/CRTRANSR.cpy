      *================================================================
      * COPYBOOK : CRTRANSR.cpy
      * SYSTEM   : Credit Risk Behaviour Scoring System
      * PURPOSE  : Daily Transaction record layout
      *            Maps to DB2 table CRISK.DAILY_TRANSACTIONS
      *            and to Oracle external table XML field structure
      *================================================================
       01  CR-TRANSACTION-REC.
           05  CTR-EXTERNAL-ACCT-NUM   PIC X(20).
      *        Maps to: DB2 EXTERNAL_ACCOUNT_NUMBER
      *        XML tag: <external_account_number>
      *        Oracle : MAIN_ACCOUNT_NUMBER
           05  CTR-SUB-ACCOUNT-NUM     PIC X(10).
      *        Maps to: DB2 SUB_ACCOUNT_NUMBER
      *        XML tag: <sub_no>
      *        Oracle : SUB_ACCOUNT_NUMBER
           05  CTR-BOOK-ID             PIC X(6).
      *        Maps to: DB2 BOOK_ID
      *        XML tag: <book_id>
      *        Oracle : COMPANY
           05  CTR-TRANSACTION-CODE    PIC X(10).
      *        Maps to: DB2 TRANSACTION_CODE
      *        XML tag: <transaction_code>
      *        Oracle : TRANSACTION_CODE
           05  CTR-TRANSACTION-AMT     PIC S9(13)V99 COMP-3.
      *        Maps to: DB2 TRANSACTION_AMT (packed decimal)
      *        XML tag: <transaction_amt>
      *        Oracle : TRANSACTION_AMOUNT
           05  CTR-TRAN-AMT-DISPLAY    PIC -9(13).99.
      *        Working display form of CTR-TRANSACTION-AMT
           05  CTR-TRAN-CATEGORY       PIC X(6).
      *        Maps to: DB2 TRAN_CATEGORY
      *        XML tag: <tran_category>
      *        Oracle : TRANSACTION_GROUP
           05  CTR-POSTED-DATE         PIC X(10).
      *        Maps to: DB2 POSTED_DATE (YYYY-MM-DD)
      *        XML tag: <posted_date>
      *        Oracle : POSTED_DATE
           05  CTR-EFFECTIVE-DATE      PIC X(10).
      *        Maps to: DB2 EFFECTIVE_DATE (YYYY-MM-DD)
      *        XML tag: <effective_date>
      *        Oracle : EFFECTIVE_DATE
           05  CTR-UNSECURED-IND       PIC X(1).
      *        Maps to: DB2 UNSECURED_IND
      *        XML tag: <unsec_ind>
      *        Oracle : UNSECURED
           05  CTR-NEW-MAIN-ACCT-NUM   PIC X(20).
      *        Maps to: DB2 NEW_MAIN_ACCOUNT_NUMBER
      *        XML tag: <New_Main_Account_Number>
      *        Oracle : NEW_MAIN_ACC_NUM
           05  CTR-NEW-LOAN-ACCT-NUM   PIC X(20).
      *        Maps to: DB2 NEW_LOAN_ACCOUNT_NUMBER
      *        XML tag: <New_Loan_Account_Number>
      *        Oracle : NEW_LOAN_ACC_NUM
           05  FILLER                  PIC X(15).
