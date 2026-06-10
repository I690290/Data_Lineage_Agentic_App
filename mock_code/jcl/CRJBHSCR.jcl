//CRJBHSCR JOB (CRISK,BHSCORE,001),
//         'CREDIT RISK BHSCORE',
//         CLASS=A,
//         MSGCLASS=X,
//         MSGLEVEL=(1,1),
//         NOTIFY=&SYSUID,
//         REGION=0M
//*
//*================================================================
//* JOB    : CRJBHSCR
//* SYSTEM : Credit Risk Behaviour Scoring System
//* MODULE : MI4014 Daily Transaction Extract Pipeline
//* PURPOSE: Orchestrate 4-step ETL pipeline:
//*   STEP010 - CRDB2EXT: Extract customer accounts from DB2
//*             CRISK.CUST_ACCOUNT_MASTER → CUST.BHSCORE.EXTRACT
//*   STEP020 - CRTXNEXT: Extract transactions from DB2
//*             CRISK.DAILY_TRANSACTIONS (driven by STEP010 output)
//*             → TRANS.BHSCORE.EXTRACT
//*   STEP030 - DFSORT:   Sort and merge STEP010 + STEP020 output
//*             CUST.BHSCORE.EXTRACT + TRANS.BHSCORE.EXTRACT
//*             → MERGED.BHSCORE.EXTRACT (transaction-enriched)
//*   STEP040 - CRXMLGEN: Generate XML from merged extract
//*             MERGED.BHSCORE.EXTRACT
//*             → MI4014_Transaction_Extract_TSB_NAM65_YYYYMMDD.xml
//*
//* OUTPUT : XML file loaded to Oracle via external table:
//*          BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_DIARIAS
//*
//* SCHEDULE : Daily, Mon-Fri, 02:00 EST
//* DEPENDS  : DB2 subsystem DBCR online
//*================================================================
//*
//JOBLIB   DD DSN=CRISK.PROD.LOADLIB,DISP=SHR
//         DD DSN=SYS1.DFSORT.SORTLIB,DISP=SHR
//*
//***********************************************************
//* STEP010: Extract customer account master data from DB2  *
//* READS : CRISK.CUST_ACCOUNT_MASTER (DB2)                 *
//* WRITES: CUST.BHSCORE.EXTRACT                            *
//***********************************************************
//STEP010  EXEC PGM=CRDB2EXT,
//         PARM='SUBSYS=DBCR',
//         COND=(4,LT)
//STEPLIB  DD DSN=CRISK.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//SYSDBOUT DD SYSOUT=*
//*    DB2 DBRM library for CRDB2EXT
//DBRM     DD DSN=CRISK.PROD.DBRMLIB(CRDB2EXT),DISP=SHR
//*    Output: Customer account extract flat file
//BHSCOEXT DD DSN=CRISK.BATCH.CUST.BHSCORE.EXTRACT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=140,BLKSIZE=27860,DSORG=PS),
//            UNIT=SYSDA
//*
//***********************************************************
//* STEP020: Extract daily transactions from DB2            *
//* READS : CRISK.DAILY_TRANSACTIONS (DB2)                  *
//*         CUST.BHSCORE.EXTRACT (input driving file)        *
//* WRITES: TRANS.BHSCORE.EXTRACT                           *
//***********************************************************
//STEP020  EXEC PGM=CRTXNEXT,
//         PARM='SUBSYS=DBCR',
//         COND=(4,LT)
//STEPLIB  DD DSN=CRISK.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//SYSDBOUT DD SYSOUT=*
//*    DBRM library for CRTXNEXT
//DBRM     DD DSN=CRISK.PROD.DBRMLIB(CRTXNEXT),DISP=SHR
//*    Input: Customer extract from STEP010 (driving file)
//BHSCOEXT DD DSN=CRISK.BATCH.CUST.BHSCORE.EXTRACT,
//            DISP=SHR
//*    Output: Transaction extract file
//BHSCOTXN DD DSN=CRISK.BATCH.TRANS.BHSCORE.EXTRACT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(200,50),RLSE),
//            DCB=(RECFM=FB,LRECL=160,BLKSIZE=27840,DSORG=PS),
//            UNIT=SYSDA
//*
//***********************************************************
//* STEP030: DFSORT - Merge and sort CUST+TRANS extracts    *
//* Performs JOINKEYS merge:                                 *
//*   F1 = CUST.BHSCORE.EXTRACT  (key: ACCT+SUB_ACCT)      *
//*   F2 = TRANS.BHSCORE.EXTRACT (key: ACCT+SUB_ACCT)      *
//* JOIN TYPE: INNER (accounts with transactions only)      *
//* Sort key: EXTERNAL_ACCT_NUM(1,20) + SUB_ACCT(21,10)    *
//*           + POSTED_DATE(desc) + TRANSACTION_CODE        *
//* READS : CUST.BHSCORE.EXTRACT  (F1)                      *
//*         TRANS.BHSCORE.EXTRACT (F2)                       *
//* WRITES: MERGED.BHSCORE.EXTRACT                          *
//***********************************************************
//STEP030  EXEC PGM=SORT,
//         COND=(4,LT)
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//*    Input file 1: Customer account extract (FB LRECL=140)
//SORTIN01 DD DSN=CRISK.BATCH.CUST.BHSCORE.EXTRACT,
//            DISP=SHR
//*    Input file 2: Transaction extract (FB LRECL=160)
//SORTIN02 DD DSN=CRISK.BATCH.TRANS.BHSCORE.EXTRACT,
//            DISP=SHR
//*    Output: Merged and sorted extract (FB LRECL=160)
//SORTOUT  DD DSN=CRISK.BATCH.MERGED.BHSCORE.EXTRACT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(250,50),RLSE),
//            DCB=(RECFM=FB,LRECL=160,BLKSIZE=27840,DSORG=PS),
//            UNIT=SYSDA
//*    SYSIN: DFSORT control cards
//SYSIN    DD *
 JOINKEYS FILES=F1,FIELDS=(1,20,A,21,10,A)
 JOINKEYS FILES=F2,FIELDS=(1,20,A,21,10,A)
 JOIN UNPAIRED,F2,ONLY
 REFORMAT FIELDS=(F2:1,160)
 SORT FIELDS=(1,20,CH,A,21,10,CH,A,77,10,CH,D,67,10,CH,A)
 OUTFIL FNAMES=SORTOUT,
        INCLUDE=(1,20,CH,NE,C' '),
        BUILD=(1,20,21,10,31,6,37,10,47,16,63,6,69,10,79,10,
               89,1,90,20,110,20)
/*
//*    END OF STEP030 SORT CARDS
//*    JOINKEYS explanation:
//*      F1 (CUST, LRECL=140): Key = pos 1-20 (EXT_ACCT) + 21-30 (SUB)
//*      F2 (TRANS, LRECL=160): Key = pos 1-20 (EXT_ACCT) + 21-30 (SUB)
//*      JOIN UNPAIRED,F2,ONLY = inner join (only matched trans records)
//*      REFORMAT = take all 160 bytes from transaction file
//*      SORT: by ACCT(1,20) ASC, SUB(21,10) ASC,
//*            POSTED_DATE(77,10) DESC, TRAN_CODE(67,10) ASC
//*      OUTFIL: filter blanks, build output with all required fields
//*
//***********************************************************
//* STEP040: Generate XML from merged extract               *
//* READS : MERGED.BHSCORE.EXTRACT                         *
//* WRITES: MI4014_Transaction_Extract_TSB_NAM65_DATE.xml  *
//***********************************************************
//STEP040  EXEC PGM=CRXMLGEN,
//         COND=(4,LT)
//STEPLIB  DD DSN=CRISK.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//*    Input: Merged and sorted extract from STEP030
//BHSCOMRG DD DSN=CRISK.BATCH.MERGED.BHSCORE.EXTRACT,
//            DISP=SHR
//*    Output: XML file to NEPTUNE_FILES_LOAD directory
//*    Filename: MI4014_Transaction_Extract_TSB_NAM65_YYYYMMDD.xml
//BHSCOXML DD DSN=NEPTUNE.FILES.LOAD.MI4014.XML,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,25),RLSE),
//            DCB=(RECFM=VB,LRECL=32004,BLKSIZE=32760,DSORG=PS),
//            UNIT=SYSDA
//*
//***********************************************************
//* STEP050: FTP transfer XML to Oracle server              *
//* Transfer: NEPTUNE.FILES.LOAD.MI4014.XML                 *
//*        → Oracle server /app/neptune/load/               *
//*          as MI4014_Transaction_Extract_TSB_NAM65_DATE.xml *
//***********************************************************
//STEP050  EXEC PGM=FTP,
//         PARM='oracle-db-server (EXIT',
//         COND=(4,LT)
//SYSPRINT DD SYSOUT=*
//OUTPUT   DD SYSOUT=*
//INPUT    DD *
 ascii
 locsite lrecl=32004 recfm=vb
 cd /app/neptune/load
 put 'NEPTUNE.FILES.LOAD.MI4014.XML'
     MI4014_Transaction_Extract_TSB_NAM65_&DATE..xml
 quit
/*
//*
//***********************************************************
//* STEP060: Cleanup intermediate work files               *
//***********************************************************
//STEP060  EXEC PGM=IEFBR14
//DEL01    DD DSN=CRISK.BATCH.CUST.BHSCORE.EXTRACT,
//            DISP=(OLD,DELETE,DELETE)
//DEL02    DD DSN=CRISK.BATCH.TRANS.BHSCORE.EXTRACT,
//            DISP=(OLD,DELETE,DELETE)
//DEL03    DD DSN=CRISK.BATCH.MERGED.BHSCORE.EXTRACT,
//            DISP=(OLD,DELETE,DELETE)
//*
//         PEND
