"""Excel import and export for one restaurant's menu."""
from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Restaurant
from .serializers import MenuCategorySerializer, PartnerMenuItemSerializer

CATEGORY_COLUMNS = ('id', 'name', 'sort_order')
ITEM_COLUMNS = (
    'id', 'name', 'category_id', 'description', 'is_veg', 'price', 'mrp',
    'is_available', 'packaging_charge', 'sort_order',
)
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 40 * 1024 * 1024


def export_menu(restaurant, template=False, *, sheet_name=None):
    workbook = Workbook(write_only=True)
    sheets = {}
    for name, columns in (('Categories', CATEGORY_COLUMNS), ('Items', ITEM_COLUMNS)):
        if sheet_name is not None and name != sheet_name:
            continue
        sheet = workbook.create_sheet(name)
        sheets[name] = sheet
        sheet.freeze_panes = 'A2'
        sheet.append(columns[1:] if template and sheet_name else columns)

    if not template and 'Categories' in sheets:
        for category in restaurant.categories.iterator():
            _append_row(sheets['Categories'], (category.pk, category.name, category.sort_order))
    if not template and 'Items' in sheets:
        for item in restaurant.items.iterator():
            _append_row(sheets['Items'], (
                item.pk, item.name, item.category_id,
                item.description, item.is_veg, item.price, item.mrp, item.is_available,
                item.packaging_charge, item.sort_order,
            ))

    output = BytesIO()
    workbook.save(output)
    workbook_name = f'menu-{sheet_name.lower()}' if sheet_name else 'menu'
    suffix = 'template' if template else restaurant.pk
    filename = f'{workbook_name}-{suffix}.xlsx'
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _append_row(sheet, values):
    # Keep names and descriptions literal even when they start with "=".
    cells = []
    for value in values:
        cell = WriteOnlyCell(sheet, value=value)
        if isinstance(value, str):
            cell.data_type = 's'
        cells.append(cell)
    sheet.append(cells)


def _sheet_rows(sheet, columns, required):
    sheet.reset_dimensions()
    rows = sheet.iter_rows(max_col=len(columns) + 1)
    header = [cell.value for cell in next(rows, ())]
    while header and header[-1] is None:
        header.pop()
    if (
        any(value not in columns for value in header)
        or len(header) != len(set(header))
        or not set(required).issubset(header)
    ):
        raise ValidationError({'header': f'Expected columns from: {", ".join(columns)}.'})

    for row_number, cells in enumerate(rows, start=2):
        if row_number > 10001:
            raise ValidationError({'row': 'Each sheet supports up to 10,000 data rows.'})
        if all(cell.value is None for cell in cells):
            continue
        if any(cell.value is not None for cell in cells[len(header):]):
            raise ValidationError({f'row {row_number}': 'Data appears in a column without a header.'})
        if any(cell.data_type in ('f', 'e') for cell in cells):
            raise ValidationError({f'row {row_number}': 'Use values instead of formulas or Excel errors.'})
        yield row_number, dict(zip(header, (cell.value for cell in cells)))


def _find_instance(queryset, value, *, field='id'):
    if value is None:
        return None
    try:
        pk = serializers.IntegerField(min_value=1, max_value=2**63 - 1).run_validation(value)
    except ValidationError as exc:
        raise ValidationError({field: exc.detail}) from exc
    instance = queryset.filter(pk=pk).first()
    if instance is None:
        raise ValidationError({field: 'This ID does not belong to the selected restaurant.'})
    return instance


def _import_sheet(sheet, restaurant, *, categories, allow_category_name=False):
    if categories:
        queryset = restaurant.categories.all()
        serializer_class = MenuCategorySerializer
        columns, required = CATEGORY_COLUMNS, ('name',)
    else:
        queryset = restaurant.items.all()
        serializer_class = PartnerMenuItemSerializer
        columns, required = ITEM_COLUMNS, ('name', 'price')
        if allow_category_name:
            columns += ('category_name',)

    counts = {'created': 0, 'updated': 0}
    seen = set()
    for row_number, values in _sheet_rows(sheet, columns, required):
        try:
            instance = _find_instance(queryset, values.pop('id', None))
            if categories and instance is None:
                name = values.get('name')
                if isinstance(name, str):
                    matches = list(queryset.filter(name__iexact=name.strip())[:2])
                    if len(matches) > 1:
                        raise ValidationError({'name': 'Multiple categories match. Supply a category ID.'})
                    instance = next(iter(matches), None)
            if instance is not None and instance.pk in seen:
                raise ValidationError({'id': 'This entry appears more than once in the sheet.'})

            if 'category_id' in values:
                if 'category_name' in values:
                    raise ValidationError({'category_id': 'Use one category column.'})
                category = _find_instance(
                    restaurant.categories.all(), values.pop('category_id'), field='category_id',
                )
                values['category'] = category.pk if category else None
            elif 'category_name' in values:
                name = values.pop('category_name')
                values['category'] = None
                if name is not None and str(name).strip():
                    matches = list(
                        restaurant.categories.filter(name__iexact=str(name).strip())[:2]
                    )
                    if len(matches) != 1:
                        raise ValidationError({'category_name': 'Use the name of a unique category in this restaurant.'})
                    values['category'] = matches[0].pk

            if 'description' in values and values['description'] is None:
                values['description'] = ''
            for field in ('sort_order', 'is_veg', 'is_available', 'packaging_charge'):
                if values.get(field) is None:
                    values.pop(field, None)

            serializer = serializer_class(
                instance, data=values, context={'restaurant': restaurant},
                partial=instance is not None,
            )
            for field in required:
                if values.get(field) is None:
                    raise ValidationError({field: 'This cell is required.'})
            serializer.is_valid(raise_exception=True)
            saved = serializer.save(restaurant=restaurant)
            seen.add(saved.pk)
            counts['created' if instance is None else 'updated'] += 1
        except ValidationError as exc:
            raise ValidationError({f'row {row_number}': exc.detail}) from exc
    return counts


def import_menu(restaurant, upload, *, sheet_name=None):
    if not upload or not upload.name.lower().endswith('.xlsx'):
        raise ValidationError({'file': 'Upload an Excel .xlsx file.'})
    if upload.size > MAX_FILE_SIZE:
        raise ValidationError({'file': 'The workbook must be 5 MB or smaller.'})

    try:
        with ZipFile(upload) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > MAX_UNCOMPRESSED_SIZE:
                raise ValidationError({'file': 'The uncompressed workbook is too large.'})
        upload.seek(0)
        workbook = load_workbook(upload, read_only=True, keep_links=False)
        try:
            sheets = set(workbook.sheetnames)
            if sheet_name is not None:
                if sheets != {sheet_name}:
                    raise ValidationError({'file': f'Use a workbook with only a {sheet_name} worksheet.'})
            elif not sheets.intersection({'Categories', 'Items'}):
                raise ValidationError({'file': 'Include a Categories or Items worksheet.'})

            result = {}
            with transaction.atomic():
                Restaurant.objects.select_for_update().get(pk=restaurant.pk)
                for name in ('Categories', 'Items'):
                    if name not in sheets:
                        continue
                    try:
                        result[name.lower()] = _import_sheet(
                            workbook[name], restaurant, categories=name == 'Categories',
                            allow_category_name=sheet_name is None,
                        )
                    except ValidationError as exc:
                        raise ValidationError({name: exc.detail}) from exc
            return result
        finally:
            workbook.close()
    except (BadZipFile, InvalidFileException, ParseError, KeyError, IndexError, ValueError,
            TypeError, OSError, RuntimeError) as exc:
        raise ValidationError({'file': 'The file could not be read as an Excel workbook.'}) from exc
    except IntegrityError as exc:
        raise ValidationError({'file': 'The menu changed during import. Refresh the export and try again.'}) from exc
