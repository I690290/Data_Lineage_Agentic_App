      *  TRANS-REC.CPY - Transaction Record Copybook
      *  Defines the layout of TRANSACTION-FILE records
       05  TI-TRANSACTION-ID    PIC X(12).
       05  TI-ACCOUNT-NUMBER    PIC 9(10).
       05  TI-TRANS-DATE        PIC X(8).
       05  TI-TRANS-TIME        PIC X(6).
       05  TI-TRANS-TYPE        PIC X(4).
           88  TRANS-PURCHASE   VALUE 'PURCH'.
           88  TRANS-REFUND     VALUE 'REFD'.
           88  TRANS-WITHDRAWAL VALUE 'WDRL'.
           88  TRANS-DEPOSIT    VALUE 'DEPO'.
       05  TI-AMOUNT            PIC S9(11)V99 COMP-3.
       05  TI-CURRENCY-CODE     PIC X(3).
       05  TI-MERCHANT-ID       PIC X(20).
       05  TI-MERCHANT-CAT      PIC X(4).
       05  TI-AUTH-CODE         PIC X(6).
       05  TI-RISK-SCORE        PIC 9(3)V99 COMP-3.
       05  TI-CHANNEL           PIC X(3).
           88  CHANNEL-ONLINE   VALUE 'ONL'.
           88  CHANNEL-ATM      VALUE 'ATM'.
           88  CHANNEL-BRANCH   VALUE 'BRN'.
           88  CHANNEL-MOBILE   VALUE 'MOB'.
       05  TI-COUNTRY-CODE      PIC X(3).
       05  TI-FILLER            PIC X(167).
