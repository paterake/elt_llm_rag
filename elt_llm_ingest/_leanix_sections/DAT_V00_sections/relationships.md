# Entity Relationships — FA Enterprise Conceptual Data Model

This document lists all 16 domain-level entity relationships in the FA Enterprise Conceptual Data Model. Each relationship section is self-contained: it names the source and target domains, states the cardinality, and lists representative entities from each domain so that any retrieved chunk carries full context.

## Relationship: ACCOUNTS → ASSETS

**ACCOUNTS** relates to (zero or more to zero or more) **ASSETS**.

## Relationship: AGREEMENTS → ASSETS

**AGREEMENTS** relates to (zero or more to zero or more) **ASSETS**.

The **AGREEMENTS** domain includes entities: Advertising Agreements, Agent Agreements, Antidoping, Assessments, Exams, Certification & Licencing, Broadcasting Rights Agreement, Claims & Settlements, Classification Types, Codes of Conduct, Commercial & Legal, Competition Agreements, Competition Governance, Declarations or Waivers....

## Relationship: AGREEMENTS → PRODUCT

**AGREEMENTS** relates to (zero or more to zero or more) **PRODUCT**.

The **AGREEMENTS** domain includes entities: Advertising Agreements, Agent Agreements, Antidoping, Assessments, Exams, Certification & Licencing, Broadcasting Rights Agreement, Claims & Settlements, Classification Types, Codes of Conduct, Commercial & Legal, Competition Agreements, Competition Governance, Declarations or Waivers....

The **PRODUCT** domain includes entities: Alcoholic Beverages, Clothing & Apparel, Coach Education & Certification, Commercial & Corporate Services, Concessions Management Services, Content Bundles, Corporate Services, Digital Merchandise, Emergency Services, Event Management Services, Event Streaming Access, Event Ticket....

## Relationship: CHANNEL → CAMPAIGN

**CHANNEL** relates to (zero or more to zero or more) **CAMPAIGN**.

The **CAMPAIGN** domain includes entities: Campaign Type, Campaign channel, Market Plan, Market Segment, Mass Promotion, Offer, Opportunity, Promotion, Targeted Promotion.

## Relationship: LOCATION → ASSETS

**LOCATION** relates to (zero or more to zero or more) **ASSETS**.

The **LOCATION** domain includes entities: Country, Ground, People Management Location, UK Geographic County, Venue.

## Relationship: PARTY → ACCOUNTS

**PARTY** relates to (zero or more to zero or more) **ACCOUNTS**.

## Relationship: PARTY → AGREEMENTS

**PARTY** relates to (zero or more to zero or more) **AGREEMENTS**.

The **AGREEMENTS** domain includes entities: Advertising Agreements, Agent Agreements, Antidoping, Assessments, Exams, Certification & Licencing, Broadcasting Rights Agreement, Claims & Settlements, Classification Types, Codes of Conduct, Commercial & Legal, Competition Agreements, Competition Governance, Declarations or Waivers....

## Relationship: PARTY → ASSETS

**PARTY** relates to (zero or more to zero or more) **ASSETS**.

## Relationship: PARTY → CAMPAIGN

**PARTY** relates to (zero or more to zero or more) **CAMPAIGN**.

The **CAMPAIGN** domain includes entities: Campaign Type, Campaign channel, Market Plan, Market Segment, Mass Promotion, Offer, Opportunity, Promotion, Targeted Promotion.

## Relationship: PARTY → LOCATION

**PARTY** relates to (zero or more to zero or more) **LOCATION**.

The **LOCATION** domain includes entities: Country, Ground, People Management Location, UK Geographic County, Venue.

## Relationship: PARTY → PARTY

**PARTY** relates to (zero or more to zero or more) **PARTY**.

## Relationship: PARTY → TRANSACTION AND EVENTS

**PARTY** relates to (zero or more to zero or more) **TRANSACTION AND EVENTS**.

The **TRANSACTION AND EVENTS** domain includes entities: Application Usage Event, Attendance & Operational Events, Behavioural & Engagement Interactions, Booking Transaction, Club Registration Event, Coaching Session Event, Concert Attendance, Content Engagement Event, Customer Transactions, Fixture Scheduling Event, Football Admin & Governance Events, Geo-Position Event....

## Relationship: PRODUCT → CAMPAIGN

**PRODUCT** relates to (zero or more to zero or more) **CAMPAIGN**.

The **PRODUCT** domain includes entities: Alcoholic Beverages, Clothing & Apparel, Coach Education & Certification, Commercial & Corporate Services, Concessions Management Services, Content Bundles, Corporate Services, Digital Merchandise, Emergency Services, Event Management Services, Event Streaming Access, Event Ticket....

The **CAMPAIGN** domain includes entities: Campaign Type, Campaign channel, Market Plan, Market Segment, Mass Promotion, Offer, Opportunity, Promotion, Targeted Promotion.

## Relationship: PRODUCT → PARTY

**PRODUCT** relates to (zero or more to zero or more) **PARTY**.

The **PRODUCT** domain includes entities: Alcoholic Beverages, Clothing & Apparel, Coach Education & Certification, Commercial & Corporate Services, Concessions Management Services, Content Bundles, Corporate Services, Digital Merchandise, Emergency Services, Event Management Services, Event Streaming Access, Event Ticket....

## Relationship: TRANSACTION AND EVENTS → ACCOUNTS

**TRANSACTION AND EVENTS** relates to (zero or more to zero or more) **ACCOUNTS**.

The **TRANSACTION AND EVENTS** domain includes entities: Application Usage Event, Attendance & Operational Events, Behavioural & Engagement Interactions, Booking Transaction, Club Registration Event, Coaching Session Event, Concert Attendance, Content Engagement Event, Customer Transactions, Fixture Scheduling Event, Football Admin & Governance Events, Geo-Position Event....

## Relationship: TRANSACTION AND EVENTS → AGREEMENTS

**TRANSACTION AND EVENTS** relates to (zero or more to zero or more) **AGREEMENTS**.

The **TRANSACTION AND EVENTS** domain includes entities: Application Usage Event, Attendance & Operational Events, Behavioural & Engagement Interactions, Booking Transaction, Club Registration Event, Coaching Session Event, Concert Attendance, Content Engagement Event, Customer Transactions, Fixture Scheduling Event, Football Admin & Governance Events, Geo-Position Event....

The **AGREEMENTS** domain includes entities: Advertising Agreements, Agent Agreements, Antidoping, Assessments, Exams, Certification & Licencing, Broadcasting Rights Agreement, Claims & Settlements, Classification Types, Codes of Conduct, Commercial & Legal, Competition Agreements, Competition Governance, Declarations or Waivers....

