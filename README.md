# CS4411Database2GroupProject

## Classroom Brainstorm Board in Real-Time using Amazon DynamoDB

Group project for **COMPSCI 4411/9538 (Databases II)** at Western University, Fall 2026, in the
*In-Depth Analysis of Data Management Systems* category (Amazon DynamoDB, Group 20).

### Overview

Relational databases can struggle when an application needs to manage large amounts of rapidly
changing data at scale. Amazon DynamoDB is a fully managed, serverless NoSQL key-value database
built for this problem. It offers automatic scaling, high availability, and low-latency access
for predictable access patterns.

To demonstrate DynamoDB, we are building a **live, collaborative brainstorm board**:

- An instructor creates a room for a topic.
- Students join the room with a code and post ideas.
- Everyone in the room sees the board update in real time.

Every action in the app (creating a room, posting an idea, loading the board) is simple and known
ahead of time, which makes it a good fit for DynamoDB's data modelling. The project showcases:

- **Single-query board loads.** Each room's data is stored together, so one query returns the whole board.
- **Conditional writes** that enforce application rules inside the database itself.
- **Time to Live (TTL)** that deletes old rooms automatically.
- **DynamoDB Streams** that push live updates to connected users.
- **Serverless scaling** from one classroom to many, with no servers to manage.

### Objectives

- Gain a practical understanding of DynamoDB's architecture (design principles, data flow, and
  scalability) and its main features (data storage, retrieval and updates, query patterns, and security).
- Build a working idea board where users can create, share, and manage ideas and interact with
  other users' ideas, for example by voting or commenting.
- Evaluate the advantages and disadvantages of DynamoDB and how it differs fundamentally from a
  traditional relational SQL database.

### Deliverables

- Project proposal
- Final report (LaTeX/Overleaf template)
- 15-minute recorded group presentation with slides and a live demo
- Complete project artifacts for reproducibility: source code, datasets, and supporting materials

Final deadline: **December 6, 2026**

### Resources

- [DynamoDB User Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Working with DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithDynamo.html)

## Group Members

| Name | Preferred Name | GitHub |
| --- | --- | --- |
| Wei Ting Wang | Annie | [@AnnieWang331](https://github.com/AnnieWang331) |
| Myoungji Cho | Roah | [@Roahcho](https://github.com/Roahcho) |
| Alexander King Perocho | Alex | [@perochoa](https://github.com/perochoa) |
| Sachin Singh | Sachin | |
| Muhammad Haadi Khawaja | Muhammad | [@mkhawa5](https://github.com/mkhawa5) |

Our Group Excel Sheet: \
https://docs.google.com/spreadsheets/d/1D12NDc1bbNykrmjbw6rxI_1_SfABOOpvLZ4hAwmwTV8/edit?pli=1&gid=0#gid=0
