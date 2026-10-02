from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_userprofile_phix_user_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='show_migration_notice',
            field=models.BooleanField(default=True, help_text='顶部通告条：提醒老用户直接用原用户名密码登录（首次登录自动迁移到 phix 账号）。'),
        ),
    ]
