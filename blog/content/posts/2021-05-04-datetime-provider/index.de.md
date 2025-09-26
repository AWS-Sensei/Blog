---
title: "Statische Eigenschaft DateTime.Now() faken mit einem DateTime Provider"
date: 2021-05-04T00:00:00+02:00
draft: false
author: "Marcel"
description: "Unser Code ist oft zeitabhängig. Wir nutzen Datum oder Uhrzeit, um Logik umzusetzen und Entscheidungen im Code zu treffen. Das Verhalten von DateTime.Now oder DateTime.UtcNow kann sich durch System, Zeitzone oder Zeitumstellung (Sommer/Winter) unterscheiden. Das bedeutet, wir müssen dies für unsere Tests kontrollieren."

images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

Unser Code ist oft zeitabhängig. Wir nutzen Datum oder Uhrzeit, um Logik umzusetzen und Entscheidungen im Code zu treffen.  
Das Verhalten von `DateTime.Now` oder `DateTime.UtcNow` kann sich je nach System, Zeitzone oder Zeitumstellung (Sommer/Winter) unterscheiden.  
Das bedeutet, dass wir dies für unsere Tests kontrollieren müssen.

Nehmen wir diese Methode als Beispiel:

```csharp
public double ReturnCurrentOffset()
{
    var result = DateTime.Now - DateTime.UtcNow;

    return result.TotalMinutes;
}
```

Wie du siehst, berechnet diese Methode den aktuellen Offset mit `DateTime.Now` und `DateTime.UtcNow`.  
Nun nehmen wir an, du möchtest dafür einen Unit Test schreiben. Wir können die statischen Eigenschaften nicht kontrollieren.  
Das Ergebnis ändert sich im Jahresverlauf und der Test wird irgendwann fehlschlagen.

Der sauberere Weg ist, ein Interface und eine Klasse zu erstellen, die die statischen `DateTime`-Eigenschaften kapseln:

```csharp
public interface IDateTimeProvider
{
    DateTime GetDateTimeNow();

    DateTime GetDateTimeUtcNow();
}
```

```csharp
public class DateTimeProvider : IDateTimeProvider
{
    public DateTime GetDateTimeNow()
    {
        return DateTime.Now;
    }

    public DateTime GetDateTimeUtcNow()
    {
        return DateTime.UtcNow;
    }
}
```

Jetzt können wir den `IDateTimeProvider` in unserem Codebeispiel verwenden:

```csharp
public class OffsetService
{
    readonly IDateTimeProvider _dateTimeProvider;

    public OffsetService(IDateTimeProvider dateTimeProvider)
    {
        _dateTimeProvider = dateTimeProvider;
    }

    public double ReturnCurrentOffset()
    {
        var now = _dateTimeProvider.GetDateTimeNow();
        var utc = _dateTimeProvider.GetDateTimeUtcNow();

        var result = now - utc;
        return result.TotalMinutes;
    }
}
```

Nun kannst du dein bevorzugtes Mocking-Framework verwenden, um Kontrolle über den `IDateTimeProvider` zu bekommen.  
Ich nutze in meinem Beispiel [xUnit.net](https://xunit.net/), [FakeItEasy](https://fakeiteasy.github.io/) und [FluentAssertion](https://fluentassertions.com/).

```csharp
[Fact]
public void OffsetServiceTest()
{
    var fakeDateTimeProvider = A.Fake<IDateTimeProvider>();

    var fakeNow = 3.May(2021).At(18, 30, 22);

    var fakeUtcNow = 3.May(2021).At(16, 30, 22);

    A.CallTo(() => fakeDateTimeProvider.GetDateTimeNow())
        .Returns(fakeNow);
    A.CallTo(() => fakeDateTimeProvider.GetDateTimeUtcNow())
        .Returns(fakeUtcNow);

    var offset = new OffsetService(fakeDateTimeProvider);

    var result = offset.ReturnCurrentOffset();

    result.Should().Be(120);
}
```

Das Ergebnis ist testbar, sauber und ich kann dir versichern, dass dieser Test wiederholbar ist – er wird jeden Tag grün bleiben.

Happy coding.
