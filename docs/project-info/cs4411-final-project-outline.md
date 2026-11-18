# Final Project - COMPSCI 4411/9538

## General Description

The course project is a significant component of your final grade and aims to deepen your understanding of the topics covered in this course. You may work on the project in a group of 3 to 5 students. To find group members, please refer to the course's discussion forum and lounge on the OWL platform.

## Project Categories

You have the option to select your project from one of the following categories:

### Research Exploration in Data Management Systems

This project category is designed for students who are interested in diving deep into the academic world of data management systems. The primary focus will be on studying and understanding research papers in this field. However, this is not just a reading exercise; you will be actively engaged in the scientific process.

Key components:

1. **Literature Review:** Begin by identifying and reading the research papers specified in the proposed topics. This will give you a foundational understanding of the current state of the field. Those papers might refer to other papers that also require reviewing to understand the topics.
2. **Reproduction of Results:** A critical component of this project is the reproduction of the results presented in the research papers. Whether you reproduce results from all the papers you study or select a subset will be determined in consultation with the instructor. This reproduction is not just an academic exercise; it is a requirement that will be included in your final report.
3. **Idea Extension:** Once you have reproduced the results, you are encouraged to extend the ideas presented in the papers. This could involve applying the concepts to new datasets, tweaking the algorithms, or even proposing entirely new methodologies.
4. **Final Report:** Summarize your findings, methodologies, and any extensions you have made in a comprehensive final report. This report should include a review of the papers you've studied, the results you've reproduced, and any extensions or new insights you've gained.
5. **Presentation:** At the end of the project, you will present your work, summarizing your journey from literature review to result reproduction and idea extension. This will be an opportunity to showcase your understanding and contributions to the field.

### In-Depth Analysis of Data Management Systems

This project category is designed for students keen on gaining a hands-on, comprehensive understanding of data management systems. Unlike the research-focused category, this project emphasizes practical analysis, evaluation, and implementation related to real-world data management systems.

Key components:

1. **System Selection:** Choose a data management system from the suggested systems that intrigues you or is relevant to your field of study. This could range from a database management system to a data warehouse or other data management solutions.
2. **Architectural Analysis:** Dive deep into the architecture of the chosen system. Understand its design principles, data flow mechanisms, and scalability. Document these findings, as they will form a crucial part of your final report.
3. **Functionalities and Features:** Investigate the system's main functionalities and features, such as data storage methods, query optimization techniques, and security measures.
4. **Case Study:** Conduct a case study to showcase the system's capabilities. This could take various forms:
   1. Developing a software application or app that utilizes the data management system for its data storage needs.
   2. An extensive exploration of the system itself, where you employ and test various functionalities and features.
5. **Final Report:** Your final report should encapsulate your architectural analysis, functionalities and features investigation, and case study findings. It should offer a holistic view of the system, from its technical architecture to its practical applications.
6. **Presentation and Demo:** Conclude the project with a presentation that summarizes your in-depth analysis and case study. This presentation should include a demo showcasing either your software application, app, or extensive usage of the system. Highlight key insights and findings, and discuss any challenges you faced and how you overcame them.

## Project Phases and Delivery

The project is divided into two main phases:

### Proposal

Submit a proposal document outlining:

1. Project title
2. Names and student IDs of all group members
3. Background and significance of the project
4. Project goals and objectives
5. Resources and tools to be used

The proposal should be submitted via OWL before the deadline and not exceed three pages. Only one group member needs to submit it. Before preparing and submitting your proposal, make sure your project topic has been confirmed by the course instructor and TAs.

### Final Deliverables

Submit the following before the final deadline:

- **Group Presentation (15 minutes):** All group members must actively participate and contribute to the presentation. Record your presentation, upload it to a streaming platform such as Microsoft Stream or YouTube, and include the link in your submission.
- **Presentation Slides:** Ensure your slides are clear, concise, and visually engaging, covering all the key points of your project.
- **Final Report:** This should provide an in-depth analysis of your project, including objectives, methodologies, results, and conclusions. Make sure it's well-structured and proofread.
- **Complete Project Artifacts for Reproducibility:** This encompasses:
  - Source Code: All programming scripts and codebases used in your project.
  - Datasets: Relevant data files or links to access them.
  - Supporting Materials: Any additional tools, libraries, or materials required to reproduce your project results. Ensure everything is organized and documented for easy replication.

## Documents Format

The proposal and the final report should be submitted in PDF format and must use the provided Overleaf [template](https://www.overleaf.com/read/wpbhqzxgrphz), which utilizes LaTeX for document creation. You can learn more about LaTeX and Overleaf [here](https://www.overleaf.com/learn/latex/Tutorials). The template is read-only; copy it to start your draft. You may use the same draft for both the proposal and the final report, expanding the latter with additional details.

## Evaluation Criteria

Your project will be peer-reviewed by students from other groups based on this [rubric](https://docs.google.com/spreadsheets/d/1FdtGDo7n6nVVSsN_xWpCUxMXRP2RbFBQp-NHPHeCjp8/edit?usp=sharing). The instructor will aggregate these peer reviews to determine your final project grade. Note that the proposal is not graded but must be approved by the instructor. If the proposal is not up to standard, it will be returned for revisions. Projects without an approved proposal will not be evaluated.

## Project Ideas

You may choose from the list of available project topics or propose your own. **Each project topic can be assigned to only one group.** Once a topic has been allocated, it will be highlighted in red and will no longer be available to other groups. All project topics, including those proposed by students, must be confirmed with the course instructor and TAs before you submit the proposal or begin work on the project. A topic is not considered approved simply because another group has not yet selected it. Proposals for topics not confirmed in advance will be returned for revision.

### Reading Research

#### Semantic Query Processing with LLMs and Multimodal Models - group 1

Traditional database operators work over explicitly represented values, but recent systems introduce semantic operators whose predicates or transformations are evaluated using LLMs or other foundation models. Examples include natural-language filters, semantic joins, classification, ranking, and aggregation over text, images, and audio. This project studies how database systems represent, optimize, and execute such operators, particularly when model inference is expensive or approximate. Students can reproduce experiments using an existing system and investigate operator ordering, model selection, caching, approximation, or trade-offs among accuracy, execution time, and monetary cost. This is substantially different from your existing TableRAG topic because the focus is on query processing and optimization inside an AI-enhanced query engine, not retrieval for prompting. Recent SemBench explicitly treats these as a new class of "semantic query processing engines."

**Readings:**

- [ThalamusDB: Approximate Query Processing on Multi-Modal Data](https://saehanjo.github.io/assets/files/thalamusdb.pdf)

#### LLM-Based SQL Query Rewriting and Query Optimization - group 36

Query rewriting and physical-plan optimization are core DBMS problems traditionally addressed using handcrafted rules, cost models, and search algorithms. Recent work investigates whether LLMs can discover equivalent but faster SQL formulations, reason about database metadata, or participate directly in query optimization. Students can compare LLM-assisted rewriting with PostgreSQL/MySQL/DuckDB optimizers on benchmarks such as TPC-H, TPC-DS, JOB, or StackOverflow. Important research questions include semantic-equivalence verification, hallucination prevention, exploitation of statistics and catalog metadata, robustness across schemas, and optimization cost versus execution-time improvement.

**Readings:**

- [R-Bot: An LLM-based Query Rewrite System](https://www.vldb.org/pvldb/vol18/p5031-li.pdf)

#### LLM-Based Database Tuning - group 19

Modern DBMSs expose many configuration parameters that can significantly affect performance, but identifying good configurations is difficult because the optimal settings depend on the workload and system environment. Recent research explores the use of large language models and LLM agents to assist with database tuning by interpreting documentation, recommending important configuration parameters, and iteratively searching for effective settings. In this project, students will study recent LLM-based approaches to database tuning and reproduce selected experiments using a system such as PostgreSQL or MySQL. Possible extensions include comparing LLM-based tuning with traditional search or Bayesian optimization methods, evaluating generalization across workloads, or studying the number of tuning trials required to reach good configurations.

**Readings:**

- [GPTuner: A Manual-Reading Database Tuning System via GPT-Guided Bayesian Optimization](https://dl.acm.org/doi/pdf/10.14778/3659437.3659449)
- [AgentTune: An Agent-Based Large Language Model Framework for Database Knob Tuning](https://dl.acm.org/doi/pdf/10.1145/3769758)

#### LLM Agents for Database Diagnosis and Performance Debugging - group 40

Diagnosing database performance problems often requires analyzing query plans, system statistics, logs, configuration settings, and documentation. Recent research investigates whether large language models and LLM agents can assist database administrators by automatically identifying the causes of performance problems and recommending corrective actions. In this project, students will study LLM-based database diagnosis and debugging systems and reproduce selected experiments on a DBMS such as PostgreSQL or MySQL. Possible extensions include evaluating diagnosis accuracy across different types of performance problems, comparing retrieval-augmented and non-retrieval approaches, or studying how reliably agents can reason over execution plans, logs, and system metrics.

**Readings:**

- [D-Bot: Database Diagnosis System using Large Language Models](https://dl.acm.org/doi/pdf/10.14778/3675034.3675043)
- [Panda: Performance Debugging for Databases using LLM Agents](https://vldb.org/cidrdb/papers/2024/p6-singh.pdf)
- [Andromeda: Debugging Database Performance Issues with Retrieval-Augmented Large Language Models](https://dl.acm.org/doi/pdf/10.1145/3722212.3725080)

#### Vector Database Query Processing, Indexing, and Hybrid Search - group 32

LLM and embedding-based applications have created a new class of database workloads involving high-dimensional vectors. The database challenge is not simply storing embeddings, but efficiently supporting approximate nearest-neighbour search together with filters, joins, SQL predicates, and other conventional database operations. Students can study vector indexing structures such as HNSW, filtered ANN search, disk-resident vector indexes, query planning, and hybrid relational/vector execution. A project could reproduce results using pgvector or another open-source system and compare recall, latency, index size, build time, and performance under different filter selectivities.

**Readings:**

- [Survey of vector database management systems](https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/vldbj2024-vectordb.pdf)
- [Efficient Vector Index Merging in Vector Databases](https://cs.purdue.edu/homes/csjgwang/pubs/SIGMOD26_HNSWMerger.pdf)

#### Database Storage Systems for AI and Machine-Learning Workloads - group 33

Most traditional database storage formats were designed for relational analytics, whereas modern ML workloads have very different access patterns involving extremely wide feature tables, tensors, images, model parameters, sparse features, and repeated training/inference. Recent database research therefore asks whether storage engines themselves should be redesigned for AI workloads. Students can investigate new columnar layouts, AI-aware compression, model/tensor storage, deduplication, and storage formats that trade accuracy for I/O and inference performance. A reproduction project could compare conventional formats against one of these AI-oriented techniques and study storage size, I/O, training/inference throughput, and accuracy.

**Readings:**

- [Bullion: A Column Store for Machine Learning](https://mail.vldb.org/cidrdb/papers/2025/p26-liao.pdf)
- [NeurStore: Efficient In-database Deep Learning Model Management System](https://dl.acm.org/doi/pdf/10.1145/3769809)

#### Approximate membership queries (AMQs) - Jinke

AMQs utilize space-efficient data structures like Bloom filters and cuckoo filters to determine if a data item exists within a large set. These data structures are integral to various real-world software systems, including Database Management Systems (DBMSs). Research in this area can focus on developing new AMQ methods, enhancements to existing techniques, or the implementation and comparative analysis of current methods.

**Readings:**

- [Bloom Filters: A Survey](https://www.eecs.harvard.edu/~michaelm/NEWWORK/postscripts/BloomFilterSurvey.pdf)
- [Cuckoo Filter: Practically Better than Bloom](http://www.cs.cmu.edu/~dga/papers/cuckoo-conext2014.pdf)
- [Vacuum Filters: More Space-Efficient and Faster Replacement for Bloom and Cuckoo Filters](https://dl.acm.org/doi/10.14778/3364324.3364333)

#### Bw-trees

Locking mechanisms for B+ trees are commonly used in applications that integrate both OLTP (Online Transaction Processing) and OLAP (Online Analytical Processing). These mechanisms can become performance bottlenecks in database systems, necessitating advanced locking techniques to mitigate the issue. Potential research projects in this area could include summarizing existing locking techniques, conducting benchmarking and performance analyses, or developing new locking mechanisms.

**Readings:**

- [A Survey of B-Tree Locking Techniques](https://dl.acm.org/doi/10.1145/1806907.1806908)
- [Building a Bw-Tree Takes More Than Just Buzz Words](http://www.cs.cmu.edu/~huanche1/publications/open_bwtree.pdf)

#### Learned indexes - group 3

One of the emerging applications of machine learning in database systems is the concept of learned indexes. In traditional database systems, indexes are data structures that speed up the retrieval of records based on specific search keys. However, learned indexes take this a step further by leveraging machine learning models to predict the position of records within a dataset based on their search keys. Instead of using conventional indexing techniques like B-trees or hash tables, learned indexes use trained models to make these predictions, potentially offering more efficient data retrieval. This innovative approach aims to optimize query performance by reducing the computational overhead associated with traditional indexing methods.

**Readings:**

- [The Case for Learned Index Structures](https://sfu-db.github.io/dbsystems/Papers/learned-index.pdf)
- [ALEX: An Updatable Adaptive Learned Index](https://dl.acm.org/doi/10.1145/3318464.3389711)

#### Hybrid column-store and row-store - group 39

Numerous database applications require a blend of both analytical processing and transactional operations. To cater to these diverse needs, hybrid data storage techniques have emerged that combine the strengths of both column-store and row-store layouts. In a traditional row-store layout, data is organized by rows, making it well-suited for transactional operations like inserts, updates, and deletes. On the other hand, column-store layouts organize data by columns, which is more efficient for analytical queries that often involve aggregations and scans over large datasets. Hybrid storage techniques aim to bring the best of both worlds by allowing databases to store data in both row and column formats. This enables optimized performance for a wide range of queries, from transactional to analytical, thereby making these hybrid systems highly effective for versatile database applications.

**Readings:**

- [Column-Stores vs. Row-Stores: How Different Are They Really?](https://dl.acm.org/doi/10.1145/1376616.1376712)
- [HYRISE—A Main Memory Hybrid Storage Engine](https://www.vldb.org/pvldb/vol4/p105-grund.pdf)
- [Bridging the Archipelago between Row-Stores and Column-Stores for Hybrid Workloads](https://15721.courses.cs.cmu.edu/spring2018/papers/10-storage/arulraj-sigmod2016.pdf)

#### Machine learning for selectivity estimation - group 13

Selectivity estimation is a cornerstone in the realm of database systems, playing a pivotal role in query optimization and performance tuning. Over the years, a multitude of techniques have been developed to address the challenges of accurate selectivity estimation. These range from traditional methods like histograms and sampling to more advanced statistical models. In recent times, deep learning has emerged as a promising approach to tackle this complex problem. Utilizing neural networks, deep learning methods aim to capture intricate patterns in the data that traditional methods may overlook, thereby potentially offering more accurate estimates. This project focuses on conducting a comprehensive comparison of these various techniques, from classical to contemporary deep learning methods. The goal is to not only evaluate their effectiveness but also to explore avenues for improving their accuracy and efficiency.

**Readings:**

- [Learning to Optimize Join Queries With Deep Reinforcement Learning](https://arxiv.org/abs/1808.03196)
- [Learned Cardinalities: Estimating Correlated Joins with Deep Learning](https://arxiv.org/pdf/1809.00677)
- [Cardinality estimation using neural networks](https://dl.acm.org/citation.cfm?id=2886444.2886453)

#### Persistent memories and database indexing

Scalable persistent memory represents the future of non-volatile computer storage, offering features traditionally associated with main memory, such as low latency and byte-addressability. These unique characteristics make persistent memory an appealing choice for implementing index structures, such as B+ Trees and their variants, in database systems. Unlike traditional disk-based storage, which has higher latency and block-level addressability, persistent memory allows for more efficient data access and manipulation. This project aims to delve into the realm of indexing techniques specifically designed for scalable persistent memory. The objective is to explore how traditional indexing methods can be adapted or new methods can be developed to fully leverage the capabilities of this next-generation memory technology.

**Readings:**

- [FPTree: A Hybrid SCM-DRAM Persistent and Concurrent B-Tree for Storage Class Memory](https://wwwdb.inf.tu-dresden.de/misc/papers/2016/Oukid_FPTree.pdf)
- [Persistent B+-Trees in Non-Volatile Main Memory](http://www.cs.cmu.edu/~chensm/papers/wbtree-vldb15.pdf)
- [Rethinking Database Algorithms for Phase Change Memory](https://www.cs.cmu.edu/~chensm/papers/pcm-db-algo-cidr11.pdf)
- [BzTree: A High-Performance Latch-free Range Index for Non-Volatile Memory](https://www.cc.gatech.edu/~jarulraj/papers/2018.bztree.vldb.pdf)

#### SQL Spark and SQL Compilation - group 12

SQL Spark is an innovative database engine that diverges from traditional query evaluation techniques by employing SQL compilation. As a novel component of the Apache Spark ecosystem, SQL Spark takes SQL queries and compiles them to be executed through Spark's functional programming API. This unique approach allows for seamless integration between relational database operations and procedural processing. By leveraging Spark's distributed computing capabilities, SQL Spark aims to deliver high-speed query execution without sacrificing the flexibility and power of SQL. The engine effectively bridges the gap between relational and procedural data processing paradigms, offering a unified platform for diverse data analytics tasks.

**Readings:**

- [Spark SQL: Relational Data Processing in Spark](https://people.csail.mit.edu/matei/papers/2015/sigmod_spark_sql.pdf)
- [A Cost Model for SPARK SQL](https://ieeexplore.ieee.org/document/8395388)

#### Learning Text-to-SQL with Large Language Models - group 23

This project introduces students to the use of large language models (LLMs) for converting natural language questions into SQL queries. Students will read recent research papers that evaluate and improve LLMs on Text-to-SQL tasks. The goal is to understand the challenges of mapping everyday language to structured database queries, explore benchmark datasets like Spider, and learn about techniques such as prompt design, few-shot learning, and evaluation methods. By the end of the project, students will gain both a theoretical and practical understanding of how LLMs can be applied to make databases easier to access through natural language.

**Readings:**

- [A Survey on Employing Large Language Models for Text-to-SQL Tasks](https://dl.acm.org/doi/10.1145/3737873)
- [SQLPrompt: In-Context Text-to-SQL with Minimal Labeled Data](https://aclanthology.org/2023.findings-emnlp.39/)
- [Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation](https://www.vldb.org/pvldb/vol17/p1132-gao.pdf)

#### Exploring Retrieval-Augmented Generation for Tabular Data - group 5

This project introduces students to recent methods that combine retrieval techniques with large language models (LLMs) to query and reason over structured tables. Students will read key research papers on TableRAG and MixRAG, which show how retrieval can be adapted to handle large tables and mixed text-table documents. The goal is to understand the challenges of scaling LLMs to tabular data, including prompt efficiency, table structure preservation, and heterogeneous document reasoning. Students will summarize the main ideas, compare the approaches, and reflect on how RAG can make databases and spreadsheets more accessible through natural language.

**Readings:**

- TableRAG: Million-Token Table Understanding with Language Models
- [Text2SQL is Not Enough: Unifying AI and Databases with TAG](https://vldb.org/cidrdb/papers/2025/p11-biswal.pdf)

### System Study

#### Apache MADlib

Apache MADlib is an open-source library designed to bring scalable analytics directly into the database environment. Unlike traditional analytics tools that require data to be exported for processing, MADlib operates in-database, thereby reducing data movement and improving efficiency. It offers data-parallel implementations across various domains, including mathematical computations, statistical analyses, graph processing, and machine learning algorithms. These implementations are designed to work with both structured and unstructured data, providing a versatile toolkit for a wide range of analytics tasks. By integrating these advanced analytics capabilities directly into the database, Apache MADlib aims to streamline the data analytics workflow, making it more efficient and scalable.

**Readings:**

- [The MADlib Analytics Library](http://vldb.org/pvldb/vol5/p1700_joehellerstein_vldb2012.pdf)
- [MADlib documentation](https://madlib.apache.org/documentation.html)

#### MySQL's alternative storage engines - group 15

A storage engine in MySQL serves as the foundational software component that the Database Management System (DBMS) relies on for performing core data operations—namely, creating, reading, updating, and deleting (CRUD) data within a database. Storage engines dictate how data is stored, indexed, and retrieved, thereby having a significant impact on the database's performance, reliability, and capabilities. MySQL offers a variety of storage engines, such as InnoDB, MyISAM, and Memory, each with its own set of features and optimizations. The objective of this project is to conduct an in-depth study of these different storage engines available in MySQL. The aim is to understand their architectures, evaluate their performance characteristics, and assess their suitability for various types of database applications.

**Readings:**

- [The InnoDB storage engine](https://dev.mysql.com/doc/refman/8.0/en/innodb-storage-engine.html)
- [Alternative storage engines in MySQL](https://dev.mysql.com/doc/refman/8.0/en/storage-engines.html)

#### PostgreSQL Tuning Tools - group 16

This project focuses on exploring the various tools and software systems designed to assist Database Administrators (DBAs) in performance-tuning PostgreSQL databases. Performance tuning is a critical aspect of database management, aimed at optimizing the speed, efficiency, and overall performance of the database system. The tools in question offer a wide array of features to facilitate this process. These include identifying productivity bottlenecks, analyzing the effectiveness of existing index configurations, providing actionable tuning recommendations and advice, and generating comprehensive performance reports. By evaluating these tools, the project aims to provide a holistic view of the available resources for performance optimization in PostgreSQL databases, thereby aiding DBAs in making informed decisions.

**Readings:**

- [dbForge Studio for PostgreSQL](https://www.devart.com/dbforge/postgresql/)
- [postgresqltuner](https://github.com/jfcoz/postgresqltuner)
- [PgBadger](https://github.com/darold/pgbadger)
- [PgMustard](https://www.postgresql.org/about/news/pgmustard-version-3-2035/)
- [PostgreSQL's statistics collector](https://www.postgresql.org/docs/current/monitoring-stats.html)

#### Apache Hadoop and Hive - group 35

Apache Hadoop is an open-source software framework designed for distributed data storage and large-scale data processing, primarily utilizing the MapReduce programming model. Built as an extension to Hadoop, Apache Hive serves as a software layer that offers a SQL-like interface, making it easier for users to interact with Hadoop's distributed file system. This project aims to delve into the intricacies of Hadoop's architecture, focusing on its distributed file system and its capabilities for handling vast amounts of data. Additionally, the project will explore how Apache Hive facilitates data access and manipulation in a Hadoop environment, effectively bridging the gap between traditional SQL databases and large-scale data processing platforms.

**Resources:**

- [Apache Hive](https://hive.apache.org/)
- [Apache Hadoop](http://hadoop.apache.org/docs/current/hadoop-project-dist/hadoop-common/SingleCluster.html)

#### Neo4j and Cypher - group 9

Neo4j is a prominent open-source graph database management system that specializes in storing data as property graphs, a flexible and intuitive data model for representing complex relationships. Cypher serves as the query language for interacting with Neo4j databases, offering a specialized syntax tailored for graph-based data manipulation. This project aims to conduct an in-depth study of Neo4j, exploring its key features, capabilities, and how it distinguishes itself from traditional Relational Database Management Systems (RDBMS). Additionally, the project will delve into the Cypher query language, examining how it facilitates data access in Neo4j and contrasting its features and syntax with those of SQL. The team undertaking this project is expected to gain a comprehensive understanding of both Neo4j and Cypher and to investigate how they differ from conventional RDBMS and SQL approaches.

**Resources:**

- [Neo4j](https://neo4j.com/docs/getting-started/current/)
- [Cypher Query Language](https://neo4j.com/developer/cypher/)

#### Apache Kafka - group 25

Apache Kafka is an open-source platform designed for handling event processing and real-time data streams. It serves as a robust and scalable solution for ingesting, storing, and processing large volumes of data in real time. This project aims to provide a comprehensive understanding of Kafka, focusing on its Application Programming Interface (API) and its specialized language for stream processing. By exploring Kafka's API, the project seeks to delve into the intricacies of how Kafka manages real-time data feeds, message queues, and distributed data storage. Additionally, the project will investigate Kafka's stream processing language, examining how it enables complex data manipulations and analytics on real-time streams.

**Resources:**

- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Kafka, The Definitive Guide](https://book.huihoo.com/pdf/confluent-kafka-definitive-guide-complete.pdf)

#### SQLite Android Bindings - group 10

SQLite is a unique SQL database engine that operates as an embedded system, reading and writing directly to standard disk files while still offering the core features of a Relational Database Management System (RDBMS). Unlike traditional RDBMSs that require a separate server process, SQLite's lightweight nature makes it particularly well-suited for mobile and embedded applications. This project aims to explore the deployment of an SQLite database instance specifically on an Android platform. The focus will be on interfacing with this SQLite database using Java, a commonly used programming language for Android development. By doing so, the project seeks to demonstrate the practicality and efficiency of using SQLite for local data storage and management in mobile applications.

**Resources:**

- [SQLite Documentation](https://sqlite.org/docs.html)
- [SQLite Android Bindings](https://sqlite.org/android/doc/trunk/www/index.wiki)

#### Apache Pulsar - group 24

Apache Pulsar is a high-performance, multi-tenant messaging solution designed for server-to-server communication. Originally developed by Yahoo, Pulsar is now maintained under the auspices of the Apache Software Foundation. It is engineered to provide robust and scalable messaging capabilities, supporting various use-cases from simple queuing to complex event streaming. Pulsar's multi-tenant architecture allows for the isolation of resources and data, making it an ideal choice for enterprises that require secure and segregated messaging environments. Its high-performance design ensures low-latency and high-throughput messaging, meeting the demands of modern, data-intensive applications.

**Resources:**

- [Pulsar Documentation](https://pulsar.apache.org/docs/en/standalone/)
- [Pulsar vs Kafka](https://pandio.com/blog/pulsar-vs-kafka-comparing-costs-and-value/)

#### MongoDB - group 28

MongoDB is a document-oriented database that aims to simplify both application development and scaling. Unlike traditional relational databases that use tables and rows, MongoDB employs a flexible, JSON-like document model, making it easier to store complex data structures. This flexibility is particularly beneficial for developers as it allows for a more agile and responsive development process. Additionally, MongoDB is built with horizontal scaling in mind, enabling it to handle large volumes of data and high traffic loads with ease. Its distributed architecture supports automatic sharding, thereby allowing the database to grow along with your application's needs.

**Resources:**

- [MongoDB Documentation](https://docs.mongodb.com/)
- [MongoDB Manual](https://docs.mongodb.com/manual/)

#### Snowflake - group 17

Snowflake is a cloud-based data warehousing solution engineered to provide scalable, high-performance data storage and analytics capabilities. Unlike traditional on-premises data warehouses, Snowflake leverages the elasticity of cloud computing to offer virtually unlimited storage and computational power. Its unique architecture separates storage and compute resources, allowing for independent scaling and optimized cost management. This project aims to conduct an in-depth study of Snowflake, focusing on its range of offerings and its underlying architecture. The objective is to understand how Snowflake's design enables efficient data storage, fast query performance, and seamless integration with various data sources and analytics tools.

**Resources:**

- [Snowflake's documentation](https://docs.snowflake.com/en/)
- [A Detailed View Inside Snowflake](https://www.snowflake.com/wp-content/uploads/2014/10/A-Detailed-View-Inside-Snowflake.pdf)

#### Apache Spark and Databricks - group 31

Databricks is a cloud-based platform that serves as a collaborative environment for data science, data engineering, and data analytics. It uniquely combines the strengths of both data warehouses and data lakes into what is termed a 'lakehouse' architecture. Built on the foundation of Apache Spark, a unified analytics engine renowned for large-scale data processing, Databricks aims to offer a comprehensive solution for diverse data-related tasks. This project aims to explore both Apache Spark and Databricks in depth, focusing on their key features, functionalities, and underlying architecture. The objective is to understand how these platforms enable efficient data processing, analytics, and collaboration, and how their architectures are designed to support scalability and performance.

**Resources:**

- [Learning Spark Lightning-Fast Data Analytics](https://pages.databricks.com/rs/094-YMS-629/images/LearningSpark2.0.pdf)
- [Databricks tutorials](https://docs.databricks.com/getting-started/tutorials/index.html)
- [Apache Spark documentation](https://spark.apache.org/docs/3.3.0/)

#### IBM Cognos - group 4

IBM Cognos Analytics is a comprehensive business intelligence platform that offers an integrated suite of analytics tools aimed at empowering organizations to make data-driven decisions. The platform combines a range of functionalities, including reporting, data modeling, analysis, dashboards, storytelling, and event management. By offering these diverse capabilities in a unified environment, Cognos Analytics enables organizations to gain a 360-degree view of their data landscape. This holistic approach facilitates better understanding and interpretation of data, thereby aiding in making effective and informed business decisions. Whether it's generating detailed reports, creating interactive dashboards, or analyzing real-time events, IBM Cognos Analytics serves as a one-stop solution for all your analytics needs.

**Resources:**

- [IBM Cognos Analytics](https://www.ibm.com/docs/en/cognos-analytics/11.1.0)

#### Tableau - group 30

Tableau is a leading visual analytics platform designed to revolutionize the way data is utilized to address challenges. It serves as a powerful tool for both individuals and organizations, enabling them to harness the full potential of their data. Unlike traditional analytics platforms that may require specialized skills, Tableau focuses on making data analytics accessible to everyone through intuitive, drag-and-drop interfaces and interactive dashboards. This user-friendly approach allows for quick insights and facilitates data-driven decision-making. Whether you're looking to create complex data visualizations, perform real-time analytics, or generate comprehensive reports, Tableau provides a versatile platform to meet a wide range of data analysis needs.

**Resources:**

- [Tableau tutorials](https://www.tableau.com/learn/training/20222)

#### Apache Cassandra - group 11

Apache Cassandra is an open-source NoSQL database that stands out for its distributed architecture, making it a trusted choice for organizations requiring scalability, high availability, and robust performance. Unlike traditional relational databases, Cassandra is designed to handle large volumes of data across multiple nodes without any single point of failure. This ensures not only linear scalability but also fault tolerance, even when deployed on commodity hardware or cloud infrastructure. These features make Cassandra an ideal platform for handling mission-critical data where both performance and reliability are paramount. Whether you're dealing with real-time analytics, high-velocity data ingestion, or large-scale data storage, Apache Cassandra offers a versatile and resilient solution.

**Resources:**

- <https://cassandra.apache.org/doc/latest/>

#### Amazon DynamoDB - group 20

Amazon DynamoDB is a fully managed NoSQL database service renowned for its speed, reliability, and effortless scalability. Unlike traditional databases that may require manual tuning and capacity planning, DynamoDB automates these processes, allowing you to focus on application logic rather than database management. It is designed to adapt to your needs, enabling you to create database tables that can accommodate varying amounts of data and different levels of request traffic. One of its standout features is its automatic data and traffic distribution across a sufficient number of servers. This ensures that the database can meet the customer-specified request capacity while storing an ever-growing volume of data, all without compromising on performance consistency and speed. Whether you're running a small application or a large-scale enterprise system, Amazon DynamoDB offers a flexible and scalable solution for your data storage needs.

**Resources:**

- [DynamoDB User Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Working with DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithDynamo.html)

#### Apache Superset - group 27

Apache Superset is an open-source data exploration and visualization platform designed to be intuitive and interactive, enabling users to quickly and easily derive insights from their data. Built on a flexible architecture, Superset integrates seamlessly with a wide array of data sources, including traditional SQL databases, NoSQL stores, and cloud-based data lakes. It offers a rich set of visualization options, ranging from simple line charts to complex geospatial analyses, all accessible through a user-friendly interface. One of its standout features is its SQL editor, which allows for advanced querying capabilities, making it a powerful tool for data analysts and business users alike. Additionally, Superset supports dashboard creation and sharing, enabling collaborative data analysis and reporting. Whether you're a data engineer looking to explore large datasets or a business analyst seeking to generate comprehensive reports, Apache Superset provides a versatile and extensible platform to meet a variety of data analytics needs.

**Resources:**

- [Apache Superset's Documentation](https://superset.apache.org/docs/intro)
- [Superset's API](https://superset.apache.org/docs/api/)

#### Extending SimpleDB with Storage, Indexing, and Transaction Features

This project extends the educational database system SimpleDB (Java) with three key features: (1) support for variable-size tuples in heap pages, replacing the current fixed-size tuple model, (2) a hash index that accelerates equality predicates and enables implementation of a hash join operator, and (3) enhancements to transaction management, such as finer-grained locking and deadlock detection. The main classes involved include HeapPage/HeapFile for storage, new index and join operator classes for query processing, and BufferPool/LockManager for transactions. Students are expected to design, implement, and write unit tests (e.g., file size comparisons, correctness of index scans, concurrency tests) to demonstrate functionality. Familiarity with Java and JUnit is required.

**Resources:**

- [SimpleDB Github Repository](https://github.com/MIT-DB-Class/simple-db-hw)

#### Firebase - group 34

Firebase is a comprehensive Backend-as-a-Service (BaaS) platform developed by Google that provides real-time data management solutions for web and mobile applications. At its core, Firebase offers two primary database services: the Realtime Database, a NoSQL cloud-hosted database that synchronizes data across clients in real-time, and Cloud Firestore, a flexible, scalable NoSQL document database with richer querying capabilities. Unlike traditional database systems that require separate server infrastructure, Firebase provides a fully managed solution with built-in features such as offline data persistence, real-time synchronization, authentication integration, and automatic scaling. This project aims to explore Firebase's data management architecture, focusing on its NoSQL data models, real-time synchronization mechanisms, security rules system, and client-side SDKs. The study will examine how Firebase's approach to data management differs from traditional RDBMS and server-centric architectures, particularly in terms of data consistency, conflict resolution, and the client-first development paradigm that Firebase enables.

**Resources:**

- Firebase Documentation
- Cloud Firestore Documentation
- Firebase Realtime Database Documentation

#### KDB+ Database - group 2

KDB+ is a high-performance column-oriented database designed particularly for time-series, streaming, and real-time data workloads. It is widely associated with financial applications where very large volumes of timestamped data must be ingested and analyzed with low latency. KDB+ integrates an in-memory compute engine with the q programming and query language and provides a specialized architecture for managing both real-time and historical data. This project aims to study the architecture of KDB+, including its columnar storage model, in-memory processing, the q language, and its real-time tick architecture. Students should develop a case study involving time-series or streaming data and investigate query performance, ingestion, and the interaction between real-time and historical data processing. KDB+ describes itself as a time-series columnar database, in-memory compute engine, and real-time streaming processor.

**Resources:**

- [KDB+ and q Documentation](https://code.kx.com/q)
- [Architecture of KDB+ Systems](https://code.kx.com/q/architecture/)
- [Starting KDB+: Tutorial](https://code.kx.com/q/learn/startingkdb/)
- [A Tour of KDB+ and the q Programming Language](https://code.kx.com/q/learn/startingkdb/)

#### Supabase - group 22

Supabase is an open-source backend platform built around PostgreSQL. Rather than introducing a new database engine, Supabase combines a full PostgreSQL database with services for automatically generated APIs, authentication, real-time database updates, file storage, server-side functions, and application development. Its architecture provides an interesting example of how a traditional relational DBMS can serve as the foundation of a modern Backend-as-a-Service platform. This project aims to study how Supabase integrates PostgreSQL with components such as PostgREST, authentication, Row-Level Security, and its Realtime infrastructure. Particular attention should be given to how database changes are propagated to clients through PostgreSQL's write-ahead log and logical replication. Students should develop an application using Supabase and analyze how its architecture differs from more conventional database-backed web applications and from platforms such as Firebase.

**Resources:**

- [Supabase Documentation](https://supabase.com/docs)
- <https://supabase.com/docs/guides/database/overview>

#### Redis - group 21

Redis is an in-memory data management system that supports a wide range of specialized data structures, including strings, hashes, lists, sets, sorted sets, streams, probabilistic structures, time-series data, JSON, and more recently vector data. Its design makes it suitable for applications such as caching, message queues, leaderboards, event processing, real-time analytics, and fast data serving. This project aims to study Redis from a database-systems perspective, including its in-memory storage model, data structures, persistence mechanisms, replication, and distributed operation through Redis Cluster. Students should experimentally investigate the performance and functionality of several Redis data structures and examine the trade-offs between Redis's RDB snapshot and Append-Only File persistence mechanisms. A case study can demonstrate Redis as a cache, streaming system, or real-time database and compare it with a conventional disk-based DBMS.

**Resources:**

- [Redis Documentation](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis Data Types](https://redis.io/docs/latest/develop/data-types/)
- [Redis Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Scaling with Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)

#### CockroachDB - group 29

CockroachDB is a distributed relational DBMS designed to provide SQL and ACID transactions while automatically distributing and replicating data across multiple machines. Internally, SQL operations are translated into operations on a distributed key-value store. Data is divided into ranges and replicated across nodes, with Raft-based consensus used to maintain consistency and Multi-Version Concurrency Control (MVCC) used for transactional processing. This project aims to study how CockroachDB combines concepts from traditional relational systems with distributed-system techniques to achieve scalability, fault tolerance, and strong transactional guarantees. Students should explore its SQL layer, distributed storage architecture, replication, transaction processing, automatic sharding, and failure recovery. A case study should deploy a small multi-node cluster and experimentally investigate scalability, replication, transaction behavior, and resilience to node failures.

**Resources:**

- CockroachDB Documentation
- CockroachDB Developer Basics and Transactions
- Architecture of a Distributed SQL Database: SQL to Key-Value Storage
- Distributed Database Architecture: Replication, Raft, and Transactions

#### MariaDB - group 7

MariaDB is an open-source relational DBMS that originated from MySQL but has developed its own database features, storage engines, optimization techniques, and distributed-data-management capabilities. One important aspect of MariaDB is its pluggable storage-engine architecture, through which different tables can use engines optimized for transactional processing, analytical workloads, write-intensive workloads, distributed storage, or other specialized purposes. This project aims to study MariaDB's overall architecture, query processing and optimization, transaction management, indexing, and storage-engine interface. Students should investigate several representative engines such as InnoDB, Aria, MyRocks, ColumnStore, or Spider and examine how storage-engine selection affects functionality and performance. The case study may also compare MariaDB with MySQL or another relational DBMS using representative OLTP and analytical workloads.

**Resources:**

- MariaDB Server Documentation
- MariaDB Architecture
- MariaDB Storage Engines Overview
- Choosing the Right MariaDB Storage Engine

#### DuckDB - group 26

DuckDB is an embedded relational database system designed specifically for analytical workloads. Similar to how SQLite provides an embedded database for transactional applications, DuckDB allows analytical SQL queries to execute directly inside applications such as Python or R without requiring a separate database server. Its implementation includes column-oriented storage, vectorized query execution, query optimization, and efficient integration with formats such as CSV and Parquet. This project aims to study the architecture and implementation of DuckDB and investigate why an embedded architecture is particularly useful for data analytics. Students should examine its storage manager, vectorized execution engine, query optimizer, indexing, and integration with external data formats. A case study should compare DuckDB with another analytical approach, such as Pandas, SQLite, or a server-based analytical DBMS, on representative analytical workloads.

**Resources:**

- DuckDB Documentation
- DuckDB: An Embeddable Analytical Database — SIGMOD 2019
- Data Management for Data Science: Towards Embedded Analytics — CIDR 2020
- Overview of DuckDB Internals
- DuckDB Vectorized Execution Format

#### Real-Time Data Pipeline Architecture with Apache Kafka and Spark Streaming - group 6

This project studies how a real-time data pipeline is built from Apache Kafka and Spark Structured Streaming. Kafka handles durable, partitioned ingestion of event streams and Spark Streaming consumes and processes those streams with windowing, aggregation, and stateful operations. Students analyze the architecture of both systems (brokers, partitions, consumer groups, and delivery guarantees on the Kafka side; micro-batch versus continuous processing, checkpointing, and fault tolerance on the Spark side) and how the two integrate. The case study reproduces a streaming pipeline of the kind used by financial firms for market-data processing, evaluating throughput, latency, and failure recovery.

#### SpacetimeDB - group 14

SpacetimeDB is a relational database that doubles as the application server: instead of a separate backend process talking to a database, application logic is uploaded into the database as WebAssembly modules and runs inside it, with clients subscribing to SQL queries and receiving live updates as the data changes. It keeps state in memory with a durable commit log, and was built to back real-time multiplayer applications. Students analyze its architecture (in-memory state plus write-ahead log, module execution, subscription and replication model, transaction handling), compare it with the conventional application-server-plus-database split, and build a case study application on top of it that exercises live subscriptions and concurrent writes.
