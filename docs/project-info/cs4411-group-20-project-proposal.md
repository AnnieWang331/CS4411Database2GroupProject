# Real-Time Brainstorm Board - Amazon DynamoDB

**Project Proposal**, Databases II (Advanced Databases)\
The University of Western Ontario, Department of Computer Science\
November 4, 2026

**Group Members:**

- Sachin Singh (ssing863)
- Myoungji Cho (mcho57)
- Muhammad Khawaja (mkhawa5)
- Wei Tin Wang (wwang939)
- Alexander King Perocho (Aperocho)

> Markdown copy of the submitted PDF (`cs4411-group-20-project-proposal.pdf`). The PDF is the
> version of record.

## Contents

1. [Background and Significance](#1-background-and-significance)
2. [Project Goals](#2-project-goals)
3. [Fit and Application of DynamoDB](#3-fit-and-application-of-dynamodb)
4. [Project Objectives](#4-project-objectives)
5. [Project Outcomes](#5-project-outcomes)
6. [Resources To Be Used](#6-resources-to-be-used)

## 1 Background and Significance

Modern web applications often need to serve large numbers of users at once, handle sudden spikes in traffic, and respond in milliseconds. Traditional relational databases handle these workloads, but they usually scale vertically and need manual capacity planning, sharding, and tuning to keep up with growth. Amazon DynamoDB is a fully managed, serverless NoSQL database designed to remove that operational burden. It provides automatic scaling, high availability, and low-latency data access [1, 3].

DynamoDB accomplishes this by storing data as key-value and document items that are distributed across many partitions based on each item's partition key. As a table's data or traffic grows, DynamoDB automatically splits and redistributes these partitions across more servers, and replicates each partition across three Availability Zones (AZ's) for durability and availability. Because every request is routed directly to the partition that holds the item's key, applications that are designed around known access patterns get consistent, single-digit millisecond performance at any scale.

To study DynamoDB in practice, we will build a collaborative, real-time brainstorm board. An instructor creates a room for a discussion topic, and students post ideas that appear live for everyone in the room. The application will serve as our case study and demonstration of DynamoDB's core features:

- Key-Based Data Modelling
- Conditional Writes
- Atomic Counters
- Time to Live (TTL)
- DynamoDB Streams

The project is significant because it shows how a NoSQL database supports interactive, collaborative workloads. It also gives us a concrete basis for evaluating DynamoDB's advantages, limitations, and fundamental differences from a traditional relational database.

## 2 Project Goals

Our goal is to build a live brainstorm board. An instructor creates a room, students join with a room code, and everyone posts and votes on ideas that appear on a shared board in real time. Through this application, we will show how DynamoDB is a strong fit for this kind of workload and how each of its features maps to a concrete requirement of the app.

## 3 Fit and Application of DynamoDB

- **Access patterns are simple and known in advance.** Creating a room, joining it, posting an idea, voting, and loading the board are all predictable operations. DynamoDB is designed for this kind of workload.
- **One query loads the whole board.** We will store each room's data under a single partition key, for example `PK = ROOM#<id>` with `SK = IDEA#<timestamp>`. A single query then retrieves the entire board.
- **Rules are enforced in the database.** Conditional writes can prevent duplicate room codes and reject posts to closed rooms. Atomic counters let many students vote on the same idea at the same time without losing updates.
- **Automatic cleanup.** TTL deletes expired rooms and their ideas without any scheduled jobs.
- **Live updates.** DynamoDB Streams capture every change to the table. An AWS Lambda function consumes the stream and pushes new ideas and votes to connected clients over WebSockets.
- **Serverless scaling.** The same design serves one classroom or many at the same time, with no servers or capacity to manage.

## 4 Project Objectives

1. **Architectural analysis.** Study and document DynamoDB's architecture, including its data model, partitioning and automatic splitting, replication across AZ's, and read consistency models.
2. **Feature analysis.** Investigate DynamoDB's main features:
   - Primary keys and secondary indexes
   - Query and scan operations
   - TTL and Streams
   - Capacity Modes
   - Security measures, including IAM access control and encryption at rest
3. **Data model design.** Design a single-table schema for the board around its known access patterns.
4. **Application development.** Implement the brainstorm board:
   - Core: Room creation, joining with a room code, posting ideas, voting, and live updates.
   - Nice-to-have: Commenting, idea moderation, and room expiry controls.
5. **Evaluation.** Measure read and write latency under simulated classroom load. Examine risks such as hot partitions when one room receives heavy traffic. Compare our design to an equivalent relational schema.
6. Publish all source code, setup instructions, and sample data in a private GitHub repository so the case study and demo can be replicated.

By the end of the project, we will have a working application that demonstrates DynamoDB's capabilities, performance, and suitability for collaborative, scalable workloads. We will also have a clear assessment of its trade-offs compared with relational SQL databases.

## 5 Project Outcomes

- Design a single-table schema (For example: `PK = ROOM#<id>`, `SK = IDEA#<timestamp>`)
- Implement rooms, posts, and votes, using atomic counters for votes
- Use conditional writes, TTL, and DynamoDB Streams
- Measure latency and throughput
- Compare against an equivalent relational schema

## 6 Resources To Be Used

- Database:
  - Amazon DynamoDB using AWS the free tier.
  - DynamoDB Local will be used for offline development and testing
- Backend:
  - An AWS SDK (boto3 for Python or the AWS SDK for Javascript v3)
  - AWS Lambda
  - AWS API Gateway WebSocket for real-time updates
- Frontend:
  - A web client, for example, React
- Data Modelling:
  - NoSQL Workbench for Amazon DynamoDB
- Collaboration and Documentation:
  - GitHub for version control and artifacts
  - LaTeX development on Overleaf for the project proposal and report
  - Discord for team member communication
  - Zoom for team meetings and progress updates

## References

[1] Amazon Web Services. What is Amazon DynamoDB? Amazon DynamoDB Developer Guide. <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html>.

[2] Amazon Web Services. Working with DynamoDB. Amazon DynamoDB Developer Guide. <https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html>.

[3] Mostafa Elhemali, Niall Gallagher, Nicholas Gordon, Joseph Idziorek, Richard Krog, Colin Lazier, Erben Mo, Akhilesh Mritunjai, Somu Perianayagam, Tim Rath, Swami Sivasubramanian, James Christopher Sorenson, III, Sroaj Sosothikul, Doug Terry, and Akshat Vig. Amazon dynamodb: A scalable, predictable performant and fully managed nosql database service. In _2022 USENIX Annual Technical Conference (USENIX ATC '22')_, pages 1037–1048. USENIX Association, 2022.
