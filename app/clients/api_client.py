from app.common.api_handlers.json_api_handler import AsyncJsonApiHandler


class ApiClient:
    """
    Class for retrieving data from urban api for gen planner
    This class provides methods to interact with the Urban API, specifically for retrieving project information.
    Attributes:
        api_handler (AsyncApiHandler): Instance of AsyncApiHandler for making API requests.
    """

    def __init__(self, api_json_handler: AsyncJsonApiHandler, max_async_extractions: int = 40):
        """
        Function initializes the UrbanApiClient with an AsyncJsonApiHandler instance.
        Args:
            api_json_handler (str): An instance of AsyncJsonApiHandler to handle API requests.
            max_async_extractions (int): Maximum number of asynchronous extractions allowed. Defaults to 40.
        """

        self.api_handler = api_json_handler
        self.max_async_extractions: int = max_async_extractions
