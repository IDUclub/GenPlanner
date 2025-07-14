import aiohttp
from loguru import logger

from app.common.exceptions.http_exception import http_exception


class AsyncJsonApiHandler:
    """
    Class for handling async requests to apies
    """

    def __init__(
        self,
        base_url: str,
    ) -> None:
        """
        Initialisation function
        Args:
            base_url (str): Base api url
        Returns:
            None
        """

        self.base_url = base_url

    @staticmethod
    async def _return_result_or_raise_error(
        response: aiohttp.ClientResponse,
        endpoint_url: str,
        params: dict,
    ) -> dict | list:
        """
        Method returns result or raise error
        :param response: aiohttp.ClientResponse
        :return: list | dict with response
        """

        if response.status in (200, 201):
            logger.info(f"Posted data with url: {response.url} and status: {response.status}")
            return await response.json()
        additional_info = await response.json()
        raise http_exception(
            response.status,
            "Error during extracting query",
            _input={"url": endpoint_url, "params": params},
            _detail=additional_info,
        )

    async def get(
        self,
        extra_url: str,
        params: dict = None,
        headers: dict = None,
    ) -> dict:
        """
        Function extracts get query within extra url

        Args:
            extra_url (str): Endpoint url
            params (dict): Query parameters
            headers (dict): Headers for queries

        Returns:
            dict: Query result in dict format
        """

        endpoint_url = self.base_url + extra_url
        async with aiohttp.ClientSession() as session:
            async with session.get(url=endpoint_url, params=params, headers=headers) as response:
                result = await self._return_result_or_raise_error(
                    response=response,
                    endpoint_url=endpoint_url,
                    params=params,
                )
                return result
