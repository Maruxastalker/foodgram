from http import HTTPStatus
from django.http import HttpResponsePermanentRedirect

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from djoser.views import UserViewSet as DjoserUserViewSet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse

from .models import (
    Error,
    Favorite,
    Ingredient,
    Recipe,
    RecipeIngredient,
    ShoppingCart,
    Subscription,
    Tag,
)

from . import filters, pagination, permissions, serializers, utils


User = get_user_model()


class UserViewSet(DjoserUserViewSet):
    def get_permissions(self):
        if self.action == 'me':
            return (IsAuthenticated(),)
        if self.action == 'retrieve':
            return (AllowAny(),)
        return super().get_permissions()

    @action(
        detail=False,
        methods=('put', 'delete'),
        permission_classes=(IsAuthenticated,),
        url_path='me/avatar',
    )
    def avatar(self, request):
        user = request.user
        if request.method == 'DELETE':
            user.avatar.delete(save=True)
            return Response(status=HTTPStatus.NO_CONTENT)
        serializer = serializers.AvatarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.avatar = serializer.validated_data['avatar']
        user.save()
        return Response(
            serializers.AvatarSerializer(user).data,
            status=HTTPStatus.OK,
        )

    @action(
        detail=False,
        methods=('GET',),
        pagination_class=pagination.LimitPageNumberPagination,
    )
    def subscriptions(self, request):
        queryset = User.objects.filter(authors__subscriber=request.user)
        serializer = serializers.ReadSubscriptionSerializer(
            self.paginate_queryset(queryset),
            many=True,
            context={'request': request},
        )
        return self.get_paginated_response(serializer.data)

    @action(
        detail=True,
        methods=(
            'POST',
            'DELETE',
        ),
    )
    def subscribe(self, request, id):
        subscriber = request.user
        author = get_object_or_404(User, pk=id)
        if request.method == 'DELETE':
            get_object_or_404(
                Subscription, author=author, subscriber=subscriber
            ).delete()
            return Response(status=HTTPStatus.NO_CONTENT)
        if subscriber == author:
            raise ValidationError(
                dict(error=Error.CANNOT_SUBSCRIBE_TO_YOURSELF)
            )
        item, created = Subscription.objects.get_or_create(
            author=author, subscriber=subscriber
        )
        if not created:
            raise ValidationError(dict(error=Error.ALREADY_SUBSCRIBED))
        return Response(
            serializers.ReadSubscriptionSerializer(
                author, context={'request': request}
            ).data,
            status=HTTPStatus.CREATED,
        )


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = serializers.TagSerializer
    pagination_class = None
    permission_classes = (AllowAny,)


class IngredientViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = serializers.IngredientSerializer
    pagination_class = None
    filter_backends = (filters.IngredientFilter,)
    search_fields = ('^name',)
    permission_classes = (AllowAny,)


class RecipeViewSet(viewsets.ModelViewSet):
    queryset = (
        Recipe.objects.prefetch_related('tags', 'ingredients')
        .select_related('author')
        .all()
    )
    permission_classes = (permissions.IsAuthorOrReadOnly,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = filters.RecipeFilterSet

    def get_serializer_class(self):
        if self.request.method in SAFE_METHODS:
            return serializers.ReadRecipeSerializer
        return serializers.WriteRecipeSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, url_path='get-link')
    def get_link(self, request, pk=None):
        short_url_code = get_object_or_404(Recipe, pk=pk).short_url_code
        short_url = request.build_absolute_uri(
            reverse('short_url', args=(short_url_code,))
        )
        return Response({'short-link': short_url}, status=HTTPStatus.OK)

    @action(detail=False)
    def download_shopping_cart(self, request):
        ingredients = (
            RecipeIngredient.objects.filter(
                recipe__shoppingcarts__user=request.user
            )
            .select_related('recipe', 'ingredient')
            .values(
                'ingredient__name',
                'ingredient__measurement_unit',
            )
            .annotate(amount=Sum('amount'))
            .order_by('ingredient__name')
        )
        recipes = Recipe.objects.filter(
            shoppingcarts__user=request.user
        ).distinct()
        return FileResponse(
            utils.make_shopping_cart_file(ingredients, recipes),
            as_attachment=True,
            filename='shopping_cart.txt',
            content_type='text/plain',
        )

    @staticmethod
    def _favorite_shopping_cart_logic(
        request, error_message_add, pk, model,
    ):
        recipe = get_object_or_404(Recipe, pk=pk)
        if request.method == 'DELETE':
            get_object_or_404(model, recipe=recipe, user=request.user).delete()
            return Response(status=HTTPStatus.NO_CONTENT)
        item, created = model.objects.get_or_create(
            user=request.user, recipe=recipe
        )
        if not created:
            raise ValidationError(dict(error=error_message_add))
        return Response(
            serializers.ShortRecipeSerializer(recipe).data,
            status=HTTPStatus.CREATED,
        )

    @action(detail=True, methods=('POST', 'DELETE'))
    def favorite(self, request, pk):
        return self._favorite_shopping_cart_logic(
            request,
            error_message_add=Error.ALREADY_FAVORITED,
            pk=pk,
            model=Favorite,
        )

    @action(detail=True, methods=('POST', 'DELETE'))
    def shopping_cart(self, request, pk):
        return self._favorite_shopping_cart_logic(
            request,
            error_message_add=Error.ALREADY_IN_SHOPPING_CART,
            pk=pk,
            model=ShoppingCart,
        )

    def handle_exception(self, exc):
        if isinstance(exc, serializers.ValidationError):
            return Response(exc.detail, status=HTTPStatus.BAD_REQUEST)
        return super().handle_exception(exc)


def recipe_shared_link(request, slug):
    try:
        recipe = Recipe.objects.get(short_url_code=slug)
    except Recipe.DoesNotExist:
        redirect_url = request.build_absolute_uri('/not_found')
    else:
        redirect_url = request.build_absolute_uri(
            f'/recipes/{recipe.id}/'
        )
    return HttpResponsePermanentRedirect(redirect_url)
