from django.db import models
from core.abstract_models import TimeStampedModel

class Country(TimeStampedModel):
    country_id = models.IntegerField(verbose_name="Country ID From Hero SMS", blank=True, null=True, unique=True)
    name = models.CharField(verbose_name="Country Name", max_length=100, blank=True, null=True)
    code = models.CharField(verbose_name="Country Code", max_length=10, blank=True, null=True)
    price = models.DecimalField(verbose_name="Price", max_digits=6, decimal_places=4, blank=True, null=True)
    is_active = models.BooleanField(verbose_name="Is Active?", default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Country"
        verbose_name_plural = "Countries"
        ordering = ['name', ]