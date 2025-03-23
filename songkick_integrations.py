import re
from fastapi import HTTPException
from helpers.classes.network_requester import NetworkRequester
from submodule_integrations.songkick.models.models import TrackUntrackLocationRequest
from submodule_integrations.models.integration import Integration
from fake_useragent import UserAgent
import requests
import aiohttp
from requests import Response
from submodule_integrations.utils.errors import (
    IntegrationAuthError,
    IntegrationAPIError,
)
from fastapi.logger import logger
from bs4 import BeautifulSoup


class SongkickIntegration(Integration):
    def __init__(self, user_agent: str = UserAgent().random):
        super().__init__("songkick")
        self.user_agent = user_agent
        self.network_requester: NetworkRequester = None
        self.url = "https://www.songkick.com"
        self.cookies = None

    @classmethod
    async def create(
        cls,
        cookies: str,
        network_requester=None,
    ):
        """
        Initialize the integration with required configurations.

        Args:
            - cookies (str): Cookies to include in network requests.
            -  network_requester (optional): A custom network requester instance. Defaults to None.
        """
        instance = cls()

        instance.network_requester = network_requester
        instance.cookies = cookies
        return instance

    async def _make_request(self, method: str, url: str, **kwargs):
        """
        Make a network request to the specified URL using the given HTTP method.

        Args:
            * method (str): The HTTP method (e.g., GET, POST).
            * url (str): The URL to send the request to.
            * **kwargs: Additional parameters for the request.

        Returns:
            * The response object from the request.
        """
        if self.network_requester:
            response = await self.network_requester.request(method, url, **kwargs)
            return response
        else:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, **kwargs) as response:
                    return await self._handle_response(response)

    @staticmethod
    async def process_html(html_response):
        response_body = await html_response.text()
        logger.debug("Attempting to process html into soup")
        soup = BeautifulSoup(response_body, "html.parser")
        return {"status_code": html_response.status, "body": soup}

    async def _handle_response(self, response: aiohttp.ClientResponse):
        """
        Handle the response from a network request, raising exceptions for errors.

        Args:
            * response (aiohttp.ClientResponse): The response object.

        Returns:
            * str | Any: Parsed JSON response if successful.

        Raises:
            * `IntegrationAuthError`: If the response status is 401.
            * `IntegrationAPIError`: For other API errors.
        """
        response_json = {}
        try:
            response_json = await response.json()
        except Exception:
            response_json = {
                "error": {"message": "Unknown error", "code": str(response.status)}
            }

        if 200 <= response.status < 204:
            return response_json

        error_message = response_json.get("error", {}).get("message", "Unknown error")
        error_code = response_json.get("error", {}).get("code", str(response.status))

        if response.status == 401:
            raise IntegrationAuthError(
                f"{self.integration_name}: {error_message}", response.status, error_code
            )
        elif response.status == 400:
            if error_message == "Resource not found.":
                raise IntegrationAPIError(
                    self.integration_name,
                    "Resource not found.",
                    response.status,
                    error_code,
                )
            else:
                raise IntegrationAPIError(
                    self.integration_name,
                    f"Bad request: {error_message}",
                    response.status,
                    error_code,
                )
        elif response.status == 500:
            raise IntegrationAPIError(
                self.integration_name,
                f"Downstream server error (translated to HTTP 501): {error_message}",
                501,
                error_code,
            )
        else:
            raise IntegrationAPIError(
                self.integration_name,
                f"{error_message} (HTTP {response.status})",
                response.status,
                error_code,
            )

    async def _setup_headers(self):
        """
        Set up headers for network requests.

        Returns:
            * dict: Headers for the network request.
        """
        _headers = {"User-Agent": self.user_agent, "Cookie": self.cookies}
        return _headers

    async def generic_make_request(self, method: str, url: str, response_key: str):
        """
        Make a generic HTTP request and return the response.

        Args:
            * method (str): The HTTP method to use (e.g., 'GET', 'POST').
            * url (str): The full URL for the API endpoint.
            * response_key (str): The key to use for the response data in the returned dictionary.

        Returns:
            * dict: A dictionary containing the response data under the given key.
        """
        headers = await self._setup_headers()
        response: Response = await self._make_request(
            method, url, headers=headers, process_response=self.process_html
        )
        return {response_key: response}

    async def search_location(self, location_name: str):

        get_locations_url = f"https://www.songkick.com/search?utf8=%E2%9C%93&type=locations&query={location_name.replace(' ', '+')}&commit=Search"

        logger.debug(f"Visiting locations url: {get_locations_url}")

        locations_response = await self.generic_make_request(
            "GET", get_locations_url, "locations"
        )

        if (
            "Sorry, we found no results for"
            in locations_response["locations"]["body"].prettify()
        ):
            logger.debug(f"No results found for {location_name}")
            raise HTTPException(
                status_code=404, detail=f"No results found for {location_name}"
            )

        soup = locations_response["locations"]["body"]

        search_results = []
        logger.debug("Parsing locations html body started")
        for li in soup.find_all("li", class_="small-city"):
            link = li.find("a", class_="search-link")
            summary = li.find("p", class_="summary")
            summary_link = summary.find("a", class_="search-link")
            name = summary_link.text.strip()
            metro_id = link["data-id"]
            url = "https://www.songkick.com" + link["href"]

            track_form = li.find(
                "form", {"data-analytics-category": "track_metro_area_button"}
            )
            if track_form:
                track_url = "https://www.songkick.com" + track_form["action"]
                authenticity_token = track_form.find(
                    "input", {"name": "authenticity_token"}
                )["value"]
                relationship_type = track_form.find(
                    "input", {"name": "relationship_type"}
                )["value"]
                subject_type = track_form.find("input", {"name": "subject_type"})[
                    "value"
                ]
                success_url = track_form.find("input", {"name": "success_url"})["value"]
            else:
                track_url = authenticity_token = relationship_type = subject_type = (
                    success_url
                ) = None

            search_results.append(
                {
                    "name": name,
                    "subject_id": metro_id,
                    "url": url,
                    "track_url": track_url,
                    "authenticity_token": authenticity_token,
                    "relationship_type": relationship_type,
                    "subject_type": subject_type,
                    "success_url": success_url,
                }
            )

            logger.debug("Parsing locations html body completed")
            return {"locations": search_results}

    async def track_untrack_location(self, request: TrackUntrackLocationRequest):
        trackings_url = "https://www.songkick.com/trackings"

        if request.untrack:
            trackings_url += "/untrack"

        logger.debug(
            f"Attempting to track/untrack location with id: {request.subject_id}"
        )

        trackings_form = {
            "utf8": "%E2%9C%93",
            "authenticity_token": request.authenticity_token,
            "relationship_type": request.relationship_type,
            "subject_id": request.subject_id,
            "subject_type": request.subject_type,
            "success_url": request.success_url,
        }

        trackings_response = self._make_request(
            "POST", trackings_url, data=trackings_form
        )
        try:
            if not '"status":"ok"' in trackings_response:
                return {"status": "Failed"}
            return trackings_response
        except Exception as exc:
            logger.debug(
                f"An error occured while attempting to track location({request.subject_id}):  {str(exc)}"
            )
            return {"status": "failed"}

    async def get_events(self, page: int | None = None):
        logger.debug("Fetching all events for user")
        get_tracked_artists_url = (
            "https://www.songkick.com/calendar?filter=tracked_artist"
        )

        if page:
            get_tracked_artists_url += f"&page={page}"

        get_tracked_artists_response: dict[str, BeautifulSoup] = (
            await self.generic_make_request("GET", get_tracked_artists_url, "artists")
        )

        if (
            get_tracked_artists_response["artists"]["status_code"] != 200
            and not "All upcoming concerts from the artists you’re tracking."
            in get_tracked_artists_response["artists"]["body"].prettify()
        ):
            logger.debug("Failed to fetch concert events")
            raise HTTPException(
                status_code=get_tracked_artists_response["artists"]["status_code"],
                detail="Failed to fetch concert events",
            )

        soup = get_tracked_artists_response["artists"]["body"]

        events = []

        event_listings = soup.find_all("li", {"title": True})
        logger.debug("Parsing html body for event information started")
        for event in event_listings:
            date_time = event.find("time")["datetime"] if event.find("time") else None
            artist_tag = event.find("p", class_="artists summary")
            artist_name = artist_tag.find("strong").text if artist_tag else None
            venue_tag = event.find("p", class_="location")
            venue_name_tag = (
                venue_tag.find("span", class_="venue-name") if venue_tag else None
            )
            venue_name = venue_name_tag.text.strip() if venue_name_tag else None
            city_state_tag = venue_tag.find_all("span")[1] if venue_tag else None
            city_state = city_state_tag.text.strip() if city_state_tag else None
            street_address_tag = (
                venue_tag.find("span", class_="street-address") if venue_tag else None
            )
            street_address = (
                street_address_tag.text.strip() if street_address_tag else None
            )
            event_url = event.find("a")["href"] if event.find("a") else None
            image_url = event.find("img")["src"] if event.find("img") else None
            ticket_url = (
                event.find("a", class_="button buy-tickets")["href"]
                if event.find("a", class_="button buy-tickets")
                else None
            )

            events.append(
                {
                    "date_time": date_time,
                    "artist": artist_name,
                    "venue": venue_name,
                    "location": city_state,
                    "street_address": street_address,
                    "event_url": (
                        f"https://www.songkick.com{event_url}" if event_url else None
                    ),
                    "image_url": f"https:{image_url}" if image_url else None,
                    "ticket_url": (
                        f"https://www.songkick.com{ticket_url}" if ticket_url else None
                    ),
                }
            )

        logger.debug("Parsing html body for event information ended")

        current_page = page if page else 1
        next_page, prev_page = None, None

        # Pagination Handling
        if len(events) > 0:
            pagination = soup.select_one(".pagination")

            if pagination:
                current_page_elem = pagination.select_one(".current")
                if current_page_elem:
                    current_page = int(current_page_elem.text.strip())

                next_page_elem = pagination.select_one(".next_page")
                if next_page_elem and "href" in next_page_elem.attrs:
                    next_page_match = re.search(r"page=(\d+)", next_page_elem["href"])
                    if next_page_match:
                        next_page = int(next_page_match.group(1))

                prev_page_elem = pagination.select_one(".previous_page:not(.disabled)")
                if prev_page_elem and "href" in prev_page_elem.attrs:
                    prev_page_match = re.search(r"page=(\d+)", prev_page_elem["href"])
                    if prev_page_match:
                        prev_page = int(prev_page_match.group(1))

        return {
            "events": events,
            "pagination": {
                "current_page": current_page,
                "next_page": next_page,
                "previous_page": prev_page,
                "has_next": next_page is not None,
                "has_previous": prev_page is not None,
            },
        }

    async def get_event_details(self, event_url):
        logger.debug("Fetching event details")
        get_event_response = await self.generic_make_request("GET", event_url, "event")

        soup = get_event_response["event"]["body"]

        date_time = (
            soup.select_one(".date-and-name p").text.strip()
            if soup.select_one(".date-and-name p")
            else None
        )
        name = (
            soup.select_one(".summary a").text.strip()
            if soup.select_one(".summary a")
            else None
        )

        location = (
            (
                soup.select_one(".location .name a").text.strip()
                + ", "
                + soup.select_one(".location span a").text.strip()
            )
            if soup.select_one(".location .name a")
            and soup.select_one(".location span a")
            else None
        )

        image_url = (
            soup.select_one(".profile-picture-wrapper img").get("src")
            if soup.select_one(".profile-picture-wrapper img")
            else None
        )

        tickets = []
        for ticket in soup.select(".buy-ticket-link"):
            vendor = (
                ticket.select_one(".vendor").text.strip()
                if ticket.select_one(".vendor")
                else "Unknown Vendor"
            )
            link = ticket.get("href")
            tickets.append(
                {"vendor": vendor, "link": f"https://www.songkick.com{link}"}
            )

        venue_name = (
            soup.select_one(".venue-info-details a").text.strip()
            if soup.select_one(".venue-info-details a")
            else None
        )
        venue_address = (
            soup.select_one(".venue-hcard span").text.strip()
            if soup.select_one(".venue-hcard span")
            else None
        )

        additional_details = {"price": None, "doors_open": None}
        additional_container = soup.select_one(".additional-details-container")
        if additional_container:
            details_text = additional_container.get_text(" ", strip=True)
            if "Price:" in details_text:
                additional_details["price"] = details_text.split("Price: ")[1].split(
                    " "
                )[0]
            if "Doors open:" in details_text:
                additional_details["doors_open"] = details_text.split("Doors open: ")[1]

        event_return = {
            "event_date_time": date_time,
            "name": name,
            "location": location,
            "image_url": (
                f"https:{image_url.replace('medium_avatar', 'huge_avatar')}"
                if image_url
                else None
            ),
            "ticketing_information": tickets,
            "venue_information": {"name": venue_name, "address": venue_address},
            "additional_details": additional_details,
        }
        logger.debug("Event details fetched successfully")
        return {"event_details": event_return}
