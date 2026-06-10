package com.example.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.PlatformTransactionManager;

import javax.sql.DataSource;

/**
 * Spring Batch configuration for the Customer Report Job.
 * Reads from CUSTSCHEMA.CUSTOMER_TABLE, processes and writes to RPTSCHEMA.REPORT_TABLE.
 */
@Configuration
@EnableBatchProcessing
public class BatchConfig {

    @Value("${batch.chunk-size:1000}")
    private int chunkSize;

    @Value("${batch.skip-limit:100}")
    private int skipLimit;

    @Value("${batch.retry-limit:3}")
    private int retryLimit;

    /** Primary DataSource — points to CUSTDB / CUSTSCHEMA */
    @Bean
    @Primary
    @ConfigurationProperties(prefix = "spring.datasource.customer")
    public DataSource customerDataSource() {
        return DataSourceBuilder.create().build();
    }

    /** Secondary DataSource — points to RPTDB / RPTSCHEMA */
    @Bean
    @ConfigurationProperties(prefix = "spring.datasource.report")
    public DataSource reportDataSource() {
        return DataSourceBuilder.create().build();
    }

    /**
     * Customer Report Job — single step: read → process → write.
     */
    @Bean
    public Job customerReportJob(
            JobRepository jobRepository,
            Step customerReportStep) {
        return new JobBuilder("customerReportJob", jobRepository)
                .start(customerReportStep)
                .build();
    }

    @Bean
    public Step customerReportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            CustomerItemReader reader,
            CustomerProcessor processor,
            CustomerItemWriter writer) {
        return new StepBuilder("customerReportStep", jobRepository)
                .<CustomerRecord, ReportRecord>chunk(chunkSize, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .skipLimit(skipLimit)
                .skip(Exception.class)
                .retryLimit(retryLimit)
                .retry(Exception.class)
                .build();
    }
}
