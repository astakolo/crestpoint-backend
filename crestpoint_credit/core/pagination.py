from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Standard pagination configuration for all list endpoints.

    Default page size is 20 records. Clients can override per-request
    using the ``page_size`` query parameter (max 100).
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return a consistent JSON envelope for paginated responses.

        Response format::

            {
                "count": <int>,
                "next": "<url or null>",
                "previous": "<url or null>",
                "results": [...]
            }
        """
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
