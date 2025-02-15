# Songkick-Unofficial-API
This project integrates with **Songkick** to allow users to search for event locations, track/untrack locations, and retrieve event details.  

## **Endpoints**  
The API exposes the following key endpoints:  

### **Location Search**  
- **GET** `/location/search?location_name=name`  
- **Response:** Returns a list of matching locations.  

### **Events Listing**  
- **GET** `/events?page=1`  
- **Response:** Returns a paginated list of events.  

### **Event Details**  
- **GET** `/event?event_url=url`  
- **Response:** Returns details like date, venue, tickets, and images.  

---

## Installation
This repo is intended to be used as a package in a larger project. https://github.com/Unofficial-APIs/Integrations

## Info
This unofficial API is built by [Integuru.ai](https://integuru.ai/). We take custom requests for new platforms or additional features for existing platforms. We also offer hosting and authentication services. If you have requests or want to work with us, reach out at richard@taiki.online.

Here's a [complete list](https://github.com/Integuru-AI/APIs-by-Integuru) of unofficial APIs built by Integuru.ai.

This repo is intended to be used as a package in a larger project: https://github.com/Integuru-AI/Integrations

