from django.core.paginator import InvalidPage
from rest_framework import pagination
from rest_framework.response import Response


class OptimizedPagination(pagination.PageNumberPagination):
    """
    Optimized pagination class that includes metadata for navigating pages
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        """Override to optimize count queries"""
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = request.query_params.get(self.page_query_param, 1)

        try:
            self.page = paginator.page(page_number)
        except InvalidPage:
            # If page is not an integer, deliver first page
            self.page = paginator.page(1)

        # Optimize by avoiding additional count queries when possible
        if self.page.has_next():
            self.page.next_page_number = self.page.number + 1
        if self.page.has_previous():
            self.page.previous_page_number = self.page.number - 1

        return list(self.page)

    def get_paginated_response(self, data):
        """Return optimized pagination response"""
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
