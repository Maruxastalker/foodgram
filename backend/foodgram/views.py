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
    def get_permission_list(self):
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
        current_user = request.user
        if request.method == 'DELETE':
            current_user.avatar.delete(save=True)
            return Response(status=HTTPStatus.NO_CONTENT)
        avatar_serializer = serializers.AvatarSerializer(data=request.data)
        avatar_serializer.is_valid(raise_exception=True)
        current_user.avatar = avatar_serializer.validated_data['avatar']
        current_user.save()
        return Response(
            serializers.AvatarSerializer(current_user).data,
            status=HTTPStatus.OK,
        )

    @action(
        detail=False,
        methods=('GET',),
        pagination_class=pagination.LimitPageNumberPagination,
    )
    def subscriptions(self, request):
        subscribed_authors = User.objects.filter(
            authors__subscriber=request.user
        )
        page = self.paginate_queryset(subscribed_authors)
        subscription_serializer = serializers.ReadSubscriptionSerializer(
            page,
            many=True,
            context={'request': request},
        )
        return self.get_paginated_response(subscription_serializer.data)

    @action(
        detail=True,
        methods=('POST', 'DELETE'),
    )
    def subscribe(self, request, id):
        subscriber = request.user
        author_to_subscribe = get_object_or_404(User, pk=id)

        if request.method == 'DELETE':
            subscription = get_object_or_404(
                Subscription,
                author=author_to_subscribe,
                subscriber=subscriber
            )
            subscription.delete()
            return Response(status=HTTPStatus.NO_CONTENT)

        if subscriber == author_to_subscribe:
            raise ValidationError(
                {'error': 'Подписка на собственный аккаунт невозможна'}
            )

        subscription, created = Subscription.objects.get_or_create(
            author=author_to_subscribe, subscriber=subscriber
        )
        if not created:
            raise ValidationError(
                {'error': 'Подписка на этого автора уже активна'}
            )

        return Response(
            serializers.ReadSubscriptionSerializer(
                author_to_subscribe, context={'request': request}
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
    search_fields = ('^name',)
    permission_classes = (AllowAny,)
    filter_backends = (filters.IngredientFilter,)


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

    def create_recipe(self, serializer):
        serializer.save(author=self.request.user)

    def get_permission_list(self):
        if self.action in [
            'create', 'favorite', 'shopping_cart', 'download_shopping_cart'
        ]:
            return [IsAuthenticated()]
        return super().get_permissions()

    def modify_recipe(self, request, *args, **kwargs):
        recipe = self.get_object()

        if not request.user.is_authenticated:
            return Response(
                {'error': 'Необходима авторизация'},
                status=HTTPStatus.UNAUTHORIZED
            )

        if recipe.author != request.user:
            return Response(
                {'error': 'Редактирование этого рецепта запрещено'},
                status=HTTPStatus.FORBIDDEN
            )

        return super().update(request, *args, **kwargs)

    def partial_modify(self, request, *args, **kwargs):
        return self.modify_recipe(request, *args, **kwargs)

    def process_exception(self, exc):
        if isinstance(exc, (Recipe.DoesNotExist, User.DoesNotExist)):
            return Response(
                {'error': 'Запрашиваемый объект не найден'},
                status=HTTPStatus.NOT_FOUND
            )
        return super().handle_exception(exc)

    @action(detail=True, url_path='get-link')
    def get_recipe_link(self, request, pk=None):
        recipe = get_object_or_404(Recipe, pk=pk)
        short_url = request.build_absolute_uri(
            reverse('short_url', args=(recipe.short_url_code,))
        )
        return Response({'short-link': short_url}, status=HTTPStatus.OK)

    @action(
        detail=False,
        methods=['GET'],
        permission_classes=[IsAuthenticated]
    )
    def download_shopping_cart(self, request):
        """
        Генерация файла со списком покупок для пользователя.
        """
        try:
            user_ingredients = (
                RecipeIngredient.objects
                .filter(recipe__shoppingcarts__user=request.user)
                .values(
                    'ingredient__name',
                    'ingredient__measurement_unit',
                )
                .annotate(total_quantity=Sum('amount'))
                .order_by('ingredient__name')
            )

            user_recipes = Recipe.objects.filter(
                shoppingcarts__user=request.user
            ).distinct()

            if not user_ingredients.exists():
                return Response(
                    {'error': 'Ваша корзина покупок пуста'},
                    status=HTTPStatus.BAD_REQUEST
                )

            shopping_list_file = utils.make_shopping_cart_file(
                user_ingredients,
                user_recipes
            )

            response = FileResponse(
                shopping_list_file,
                as_attachment=True,
                filename='shopping_list.txt',
                content_type='text/plain; charset=utf-8'
            )

            return response

        except Exception as e:
            print(f"Ошибка при создании списка покупок: {e}")
            return Response(
                {'error': 'Произошла ошибка при создании списка покупок'},
                status=HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def manage_recipe_relation(
        self, request, error_message, recipe_id, relation_model
    ):
        user = request.user
        recipe = get_object_or_404(Recipe, pk=recipe_id)

        if request.method == 'DELETE':
            relation = get_object_or_404(
                relation_model,
                user=user,
                recipe=recipe
            )
            relation.delete()
            return Response(status=HTTPStatus.NO_CONTENT)

        if relation_model.objects.filter(user=user, recipe=recipe).exists():
            return Response(
                {'error': error_message},
                status=HTTPStatus.BAD_REQUEST
            )

        relation_model.objects.create(user=user, recipe=recipe)
        recipe_data = serializers.ShortRecipeSerializer(recipe)
        return Response(recipe_data.data, status=HTTPStatus.CREATED)

    @action(detail=True, methods=('POST', 'DELETE'))
    def favorite(self, request, pk):
        return self.manage_recipe_relation(
            request,
            error_message='Этот рецепт уже в избранном',
            recipe_id=pk,
            relation_model=Favorite,
        )

    @action(detail=True, methods=('POST', 'DELETE'))
    def shopping_cart(self, request, pk):
        return self.manage_recipe_relation(
            request,
            error_message='Рецепт уже в списке покупок',
            recipe_id=pk,
            relation_model=ShoppingCart,
        )


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
